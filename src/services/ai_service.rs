use anyhow::{Result, Context};
use reqwest::Client;
use serde_json::{json, Value};
use std::sync::Arc;
use tracing::{info, warn, error};

use crate::config::Config;
use crate::models::ContentAnalysis;

pub struct AIService {
    config: Arc<Config>,
    http_client: Client,
}

impl AIService {
    pub fn new(config: &Arc<Config>) -> Result<Self> {
        let http_client = Client::builder()
            .timeout(std::time::Duration::from_secs(30))
            .build()
            .context("创建HTTP客户端失败")?;

        Ok(Self {
            config: config.clone(),
            http_client,
        })
    }

    /// 分析内容是否为垃圾信息或骚扰
    pub async fn analyze_content(&self,
        content: &str,
        media_description: Option<&str>,
    ) -> Result<ContentAnalysis> {
        if !self.config.enable_ai_filter {
            return Ok(ContentAnalysis {
                is_spam: false,
                is_harassment: false,
                confidence: 0,
                reason: None,
            });
        }

        // 优先使用Gemini
        if self.config.gemini_api_key.is_some() {
            match self.analyze_with_gemini(content, media_description).await {
                Ok(result) => return Ok(result),
                Err(e) => warn!("Gemini分析失败: {}, 尝试OpenAI", e),
            }
        }

        // 回退到OpenAI
        if self.config.openai_api_key.is_some() {
            return self.analyze_with_openai(content, media_description).await;
        }

        // 没有配置AI，放行
        Ok(ContentAnalysis {
            is_spam: false,
            is_harassment: false,
            confidence: 0,
            reason: None,
        })
    }

    async fn analyze_with_gemini(
        &self,
        content: &str,
        media_description: Option<&str>,
    ) -> Result<ContentAnalysis> {
        let api_key = self.config.gemini_api_key.as_ref().unwrap();
        let url = format!(
            "https://generativelanguage.googleapis.com/v1/models/{}:generateContent?key={}",
            self.config.gemini_model,
            api_key
        );

        let prompt = self.build_analysis_prompt(content, media_description);

        let body = json!({
            "contents": [{
                "parts": [{
                    "text": prompt
                }]
            }],
            "generationConfig": {
                "temperature": 0.1,
                "maxOutputTokens": 256
            }
        });

        let response = self.http_client
            .post(&url)
            .json(&body)
            .send()
            .await
            .context("Gemini API请求失败")?;

        if !response.status().is_success() {
            let error_text = response.text().await.unwrap_or_default();
            anyhow::bail!("Gemini API错误: {}", error_text);
        }

        let json: Value = response.json().await.context("解析Gemini响应失败")?;
        let text = json["candidates"][0]["content"]["parts"][0]["text"]
            .as_str()
            .unwrap_or("");

        self.parse_analysis_response(text)
    }

    async fn analyze_with_openai(
        &self,
        content: &str,
        media_description: Option<&str>,
    ) -> Result<ContentAnalysis> {
        let api_key = self.config.openai_api_key.as_ref().unwrap();
        let url = format!("{}/chat/completions", self.config.openai_base_url);

        let prompt = self.build_analysis_prompt(content, media_description);

        let body = json!({
            "model": self.config.openai_model,
            "messages": [
                {
                    "role": "system",
                    "content": "你是一个内容审核助手，只返回JSON格式的分析结果。"
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "temperature": 0.1,
            "max_tokens": 256
        });

        let response = self.http_client
            .post(&url)
            .header("Authorization", format!("Bearer {}", api_key))
            .json(&body)
            .send()
            .await
            .context("OpenAI API请求失败")?;

        if !response.status().is_success() {
            let error_text = response.text().await.unwrap_or_default();
            anyhow::bail!("OpenAI API错误: {}", error_text);
        }

        let json: Value = response.json().await.context("解析OpenAI响应失败")?;
        let text = json["choices"][0]["message"]["content"]
            .as_str()
            .unwrap_or("");

        self.parse_analysis_response(text)
    }

    fn build_analysis_prompt(&self,
        content: &str,
        media_description: Option<&str>,
    ) -> String {
        let media_part = media_description
            .map(|d| format!("\n附带媒体描述: {}", d))
            .unwrap_or_default();

        format!(r#"请分析以下用户消息，判断是否为垃圾信息(spam)或骚扰信息(harassment)。

用户消息: "{}{}

请以JSON格式返回分析结果：
{{
    "is_spam": true/false,
    "is_harassment": true/false,
    "confidence": 0-100,
    "reason": "判断理由"
}}

注意：
- 垃圾信息指广告、推销、诈骗等无关内容
- 骚扰信息指辱骂、威胁、恶意内容
- confidence是置信度，越高表示越确定
- 请只返回JSON，不要其他内容"#, content, media_part)
    }

    fn parse_analysis_response(&self,
        text: &str,
    ) -> Result<ContentAnalysis> {
        // 尝试从文本中提取JSON
        let json_text = if text.contains("```json") {
            text.split("```json").nth(1)
                .and_then(|s| s.split("```").next())
                .unwrap_or(text)
        } else if text.contains("```") {
            text.split("```").nth(1)
                .unwrap_or(text)
        } else {
            text
        }.trim();

        let json: Value = serde_json::from_str(json_text)
            .context("解析AI响应JSON失败")?;

        let is_spam = json["is_spam"].as_bool().unwrap_or(false);
        let is_harassment = json["is_harassment"].as_bool().unwrap_or(false);
        let confidence = json["confidence"].as_i64().unwrap_or(0) as i32;
        let reason = json["reason"].as_str().map(|s| s.to_string());

        Ok(ContentAnalysis {
            is_spam,
            is_harassment,
            confidence,
            reason,
        })
    }

    /// 生成验证问题
    pub async fn generate_verification_question(
        &self,
    ) -> Result<(String, String)> {
        let prompt = r#"请生成一道简单的人机验证问题，用于区分人类和机器人。

要求：
1. 问题应该是简单的逻辑题或数学题
2. 答案应该简短（一个单词或数字）
3. 避免常识性问题（可能被AI轻易回答）

请以JSON格式返回：
{
    "question": "问题内容",
    "answer": "正确答案"
}

例如：
{
    "question": "3 + 5 = ?",
    "answer": "8"
}
或：
{
    "question": "红色和蓝色混合是什么颜色？",
    "answer": "紫色"
}"#;

        // 优先使用Gemini
        if let Some(api_key) = &self.config.gemini_api_key {
            match self.call_gemini(prompt).await {
                Ok(response) => {
                    if let Ok((q, a)) = self.parse_qa_response(&response).await {
                        return Ok((q, a));
                    }
                }
                Err(e) => warn!("Gemini生成问题失败: {}", e),
            }
        }

        // 回退到OpenAI
        if let Some(_) = &self.config.openai_api_key {
            let response = self.call_openai(prompt).await?;
            return self.parse_qa_response(&response).await;
        }

        // 没有AI配置，使用默认问题
        Ok((
            "请回答：2 + 3 = ?".to_string(),
            "5".to_string(),
        ))
    }

    /// 生成解封挑战问题
    pub async fn generate_unblock_challenge(
        &self,
        reason: Option<&str>,
    ) -> Result<(String, String)> {
        let reason_text = reason.unwrap_or("违反使用规则");
        let prompt = format!(r#"用户因"{}"被拉黑，现在想要解封。
请生成一道需要思考的问题作为解封挑战，问题应该有一定难度，需要真正的思考才能回答。

请以JSON格式返回：
{{
    "question": "挑战问题（请用中文）",
    "answer": "参考答案（可以有多个正确答案）"
}}

问题应该让用户展示他们理解了规则或愿意遵守规则。"#, reason_text);

        // 优先使用Gemini
        if let Some(_) = &self.config.gemini_api_key {
            match self.call_gemini(&prompt).await {
                Ok(response) => {
                    if let Ok((q, a)) = self.parse_qa_response(&response).await {
                        return Ok((q, a));
                    }
                }
                Err(e) => warn!("Gemini生成挑战失败: {}", e),
            }
        }

        // 回退到OpenAI
        if let Some(_) = &self.config.openai_api_key {
            let response = self.call_openai(&prompt).await?;
            return self.parse_qa_response(&response).await;
        }

        // 默认挑战
        Ok((
            "请说明你会如何正确使用这个机器人的双向聊天功能，以及不会发送哪些类型的消息。".to_string(),
            "合理使用".to_string(),
        ))
    }

    /// 基于知识库生成自动回复
    pub async fn generate_auto_reply(
        &self,
        query: &str,
        knowledge: &str,
    ) -> Result<Option<String>> {
        let prompt = format!(r#"基于以下知识库内容，回答用户的问题。
如果知识库中没有相关信息，请回复"NO_ANSWER"。

知识库内容：
{}

用户问题：{}

请直接给出回答，不要提及知识库。如果完全无法回答，只回复"NO_ANSWER"。"#, knowledge, query);

        let response = if self.config.gemini_api_key.is_some() {
            self.call_gemini(&prompt).await?
        } else if self.config.openai_api_key.is_some() {
            self.call_openai(&prompt).await?
        } else {
            return Ok(None);
        };

        if response.contains("NO_ANSWER") || response.trim().is_empty() {
            Ok(None)
        } else {
            Ok(Some(response.trim().to_string()))
        }
    }

    async fn call_gemini(&self,
        prompt: &str,
    ) -> Result<String> {
        let api_key = self.config.gemini_api_key.as_ref().unwrap();
        let url = format!(
            "https://generativelanguage.googleapis.com/v1/models/{}:generateContent?key={}",
            self.config.gemini_model,
            api_key
        );

        let body = json!({
            "contents": [{
                "parts": [{
                    "text": prompt
                }]
            }],
            "generationConfig": {
                "temperature": 0.7,
                "maxOutputTokens": 1024
            }
        });

        let response = self.http_client
            .post(&url)
            .json(&body)
            .send()
            .await?;

        if !response.status().is_success() {
            let error_text = response.text().await.unwrap_or_default();
            anyhow::bail!("Gemini API错误: {}", error_text);
        }

        let json: Value = response.json().await?;
        let text = json["candidates"][0]["content"]["parts"][0]["text"]
            .as_str()
            .unwrap_or("")
            .to_string();

        Ok(text)
    }

    async fn call_openai(&self,
        prompt: &str,
    ) -> Result<String> {
        let api_key = self.config.openai_api_key.as_ref().unwrap();
        let url = format!("{}/chat/completions", self.config.openai_base_url);

        let body = json!({
            "model": self.config.openai_model,
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "temperature": 0.7,
            "max_tokens": 1024
        });

        let response = self.http_client
            .post(&url)
            .header("Authorization", format!("Bearer {}", api_key))
            .json(&body)
            .send()
            .await?;

        if !response.status().is_success() {
            let error_text = response.text().await.unwrap_or_default();
            anyhow::bail!("OpenAI API错误: {}", error_text);
        }

        let json: Value = response.json().await?;
        let text = json["choices"][0]["message"]["content"]
            .as_str()
            .unwrap_or("")
            .to_string();

        Ok(text)
    }

    async fn parse_qa_response(
        &self,
        text: &str,
    ) -> Result<(String, String)> {
        // 尝试提取JSON
        let json_text = if text.contains("```json") {
            text.split("```json").nth(1)
                .and_then(|s| s.split("```").next())
                .unwrap_or(text)
        } else if text.contains("```") {
            text.split("```").nth(1)
                .unwrap_or(text)
        } else {
            text
        }.trim();

        let json: Value = serde_json::from_str(json_text)
            .context("解析QA JSON失败")?;

        let question = json["question"]
            .as_str()
            .context("缺少question字段")?
            .to_string();
        let answer = json["answer"]
            .as_str()
            .context("缺少answer字段")?
            .to_string();

        Ok((question, answer))
    }
}
