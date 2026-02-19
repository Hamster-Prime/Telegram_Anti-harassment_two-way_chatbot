use anyhow::{Result, Context};
use std::sync::Arc;
use tracing::{info, warn};

use crate::config::Config;
use crate::db::Database;
use crate::models::VerificationResult;
use crate::services::AIService;

pub struct VerificationService {
    db: Database,
    config: Arc<Config>,
    ai_service: AIService,
}

impl VerificationService {
    pub fn new(
        db: Database,
        config: Arc<Config>,
        ai_service: AIService,
    ) -> Self {
        Self {
            db,
            config,
            ai_service,
        }
    }

    /// 为用户创建验证会话
    pub async fn create_verification(
        &self,
        user_id: i64,
    ) -> Result<(String, String)> {
        // 检查是否已有活跃会话
        if let Some(existing) = self.db.get_verification_session(user_id).await? {
            return Ok((existing.question, expected_answer_to_hint(&existing.expected_answer)));
        }

        // 生成验证问题
        let (question, answer) = self.ai_service.generate_verification_question().await?;

        // 创建会话
        self.db.create_verification_session(
            user_id,
            question.clone(),
            answer.clone(),
            self.config.max_verification_attempts,
            self.config.verification_timeout,
        ).await?;

        let hint = expected_answer_to_hint(&answer);

        Ok((question, hint))
    }

    /// 验证用户答案
    pub async fn verify_answer(
        &self,
        user_id: i64,
        answer: &str,
    ) -> Result<VerificationResult> {
        let session = match self.db.get_verification_session(user_id).await? {
            Some(s) => s,
            None => return Ok(VerificationResult::Failed("没有活跃的验证会话".to_string())),
        };

        // 检查是否过期
        if chrono::Utc::now() > session.expires_at {
            self.db.complete_verification(user_id, false).await?;
            return Ok(VerificationResult::Expired);
        }

        // 检查尝试次数
        if session.attempts >= session.max_attempts {
            self.db.complete_verification(user_id, false).await?;
            return Ok(VerificationResult::MaxAttemptsReached);
        }

        // 增加尝试次数
        self.db.increment_verification_attempt(user_id).await?;

        // 检查答案（不区分大小写，去除空格）
        let user_answer = answer.trim().to_lowercase();
        let expected = session.expected_answer.trim().to_lowercase();

        // 支持多个正确答案（用逗号分隔）
        let answers: Vec<&str> = expected.split(',').collect();
        let is_correct = answers.iter().any(|a| user_answer == a.trim());

        if is_correct {
            self.db.complete_verification(user_id, true).await?;
            info!("用户 {} 通过验证", user_id);
            Ok(VerificationResult::Success)
        } else {
            let remaining = session.max_attempts - session.attempts - 1;
            let msg = if remaining > 0 {
                format!("答案错误，还剩 {} 次尝试机会", remaining)
            } else {
                "答案错误，验证失败".to_string()
            };

            if remaining == 0 {
                self.db.complete_verification(user_id, false).await?;
                return Ok(VerificationResult::MaxAttemptsReached);
            }

            Ok(VerificationResult::Failed(msg))
        }
    }

    /// 检查用户是否需要验证
    pub async fn needs_verification(&self,
        user_id: i64,
    ) -> Result<bool> {
        if !self.config.verification_enabled {
            return Ok(false);
        }

        let user = match self.db.get_user(user_id).await? {
            Some(u) => u,
            None => return Ok(true), // 新用户需要验证
        };

        // 已验证或豁免的用户不需要
        if user.is_verified || user.is_exempt {
            return Ok(false);
        }

        // 检查是否有活跃验证会话
        if let Some(session) = self.db.get_verification_session(user_id).await? {
            // 检查是否过期
            if chrono::Utc::now() <= session.expires_at {
                return Ok(true);
            }
        }

        Ok(true)
    }

    /// 检查用户是否已通过验证
    pub async fn is_verified(&self,
        user_id: i64,
    ) -> Result<bool> {
        let user = self.db.get_user(user_id).await?;
        Ok(user.map(|u| u.is_verified || u.is_exempt).unwrap_or(false))
    }

    /// 清理过期的验证会话
    pub async fn cleanup_expired(&self) -> Result<()> {
        self.db.cleanup_expired_verifications().await
    }

    /// 获取验证问题给用户
    pub async fn get_verification_prompt(&self,
        user_id: i64,
    ) -> Result<String> {
        let (question, _) = self.create_verification(user_id).await?;

        Ok(format!(
            "欢迎使用！在使用本机器人之前，请完成以下人机验证:\n\n{}\n\n" \
            "请直接回复答案。你有 {} 次尝试机会，限时 {} 分钟。",
            question,
            self.config.max_verification_attempts,
            self.config.verification_timeout / 60
        ))
    }
}

/// 将预期答案转换为提示（隐藏部分信息）
fn expected_answer_to_hint(answer: &str) -> String {
    // 如果答案是数字，显示位数提示
    if answer.chars().all(|c| c.is_ascii_digit()) {
        return format!("{}位数字", answer.len());
    }

    // 如果是短答案，显示长度
    if answer.len() <= 5 {
        return format!("{}个字符", answer.len());
    }

    // 长答案只显示提示
    "请根据问题内容回答".to_string()
}
