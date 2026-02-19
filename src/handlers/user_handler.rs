use teloxide::prelude::*;
use teloxide::types::{ParseMode, ReplyParameters};
use tracing::{info, warn};

use crate::config::Config;
use crate::db::Database;
use crate::models::{MediaType, VerificationResult};
use crate::services::{AIService, BlacklistService, ThreadManager, VerificationService, RateLimiter};
use std::sync::Arc;
use std::sync::OnceLock;

static RATE_LIMITER: OnceLock<RateLimiter> = OnceLock::new();

fn get_rate_limiter(config: &Config) -> &RateLimiter {
    RATE_LIMITER.get_or_init(|| RateLimiter::new(config.max_messages_per_minute))
}

pub async fn handle_private_message(
    bot: Bot,
    msg: Message,
    config: Arc<Config>,
    db: Database,
    ai_service: AIService,
) -> anyhow::Result<()> {
    let user = msg.from().context("无法获取用户信息")?;
    let chat_id = msg.chat.id;

    // 速率限制检查
    let rate_limiter = get_rate_limiter(&config);
    if !rate_limiter.check_rate_limit(user.id.0) {
        bot.send_message(chat_id, 
            "发送消息过于频繁，请稍后再试。"
        ).await?;
        return Ok(());
    }

    // 获取或创建用户
    let db_user = db.get_or_create_user(
        user.id.0,
        user.username.clone(),
        user.first_name.clone(),
        user.last_name.clone(),
    ).await?;

    // 检查是否在黑名单中
    if db_user.is_blocked {
        bot.send_message(chat_id, 
            "你已被限制使用此机器人。"
        ).await?;
        return Ok(());
    }

    // 验证检查
    let verification = VerificationService::new(db.clone(), config.clone(), ai_service.clone());
    if verification.needs_verification(user.id.0).await? {
        // 用户发送的是验证答案
        if let Some(text) = msg.text() {
            match verification.verify_answer(user.id.0, text).await? {
                VerificationResult::Success => {
                    bot.send_message(chat_id, 
                        "验证通过！现在可以正常使用机器人了。"
                    ).await?;
                    return Ok(());
                }
                VerificationResult::Failed(reason) => {
                    bot.send_message(chat_id, reason).await?;
                    return Ok(());
                }
                VerificationResult::Expired => {
                    let prompt = verification.get_verification_prompt(user.id.0).await?;
                    bot.send_message(chat_id, prompt).await?;
                    return Ok(());
                }
                VerificationResult::MaxAttemptsReached => {
                    let blacklist = BlacklistService::new(db.clone(), config.clone());
                    blacklist.block_user(
                        user.id.0, 
                        Some("验证失败次数过多".to_string()),
                        bot.get_me().await?.id.0,
                        Some(24)
                    ).await?;
                    bot.send_message(chat_id, 
                        "验证失败次数过多，你已被临时限制使用。"
                    ).await?;
                    return Ok(());
                }
            }
        }

        // 需要验证但还没回答
        let prompt = verification.get_verification_prompt(user.id.0).await?;
        bot.send_message(chat_id, prompt).await?;
        return Ok(());
    }

    // AI内容过滤（非豁免用户）
    if config.enable_ai_filter && !db_user.is_exempt {
        let content = msg.text().map(|t| t.to_string())
            .or_else(|| msg.caption().map(|c| c.to_string()))
            .unwrap_or_default();

        let media_desc = get_media_description(&msg);

        if !content.is_empty() || media_desc.is_some() {
            match ai_service.analyze_content(&content, media_desc.as_deref()).await {
                Ok(analysis) => {
                    if analysis.confidence >= config.ai_confidence_threshold {
                        if analysis.is_spam {
                            bot.send_message(chat_id, 
                                "你的消息被识别为垃圾信息，已被拦截。"
                            ).await?;
                            return Ok(());
                        }
                        if analysis.is_harassment {
                            bot.send_message(chat_id, 
                                "你的消息包含不当内容，已被拦截。"
                            ).await?;
                            return Ok(());
                        }
                    }
                }
                Err(e) => {
                    warn!("AI内容分析失败: {}", e);
                    // AI失败时不拦截，放行
                }
            }
        }
    }

    // 自动回复（基于知识库）
    if let Some(text) = msg.text() {
        let entries = db.search_knowledge_entries(text).await?;
        if !entries.is_empty() {
            let knowledge = entries.iter()
                .map(|e| format!("{}: {}", e.keyword, e.response))
                .collect::<Vec<_>>()
                .join("\n");

            match ai_service.generate_auto_reply(text, &knowledge).await {
                Ok(Some(reply)) => {
                    // 发送自动回复
                    bot.send_message(chat_id, &reply)
                        .parse_mode(ParseMode::Markdown)
                        .await?;
                }
                _ => {}
            }
        }
    }

    // 转发到论坛话题
    let thread_manager = ThreadManager::new(db.clone(), config.clone());
    let thread_id = thread_manager.get_or_create_thread(&bot, &db_user
    ).await?;

    // 转发消息
    match thread_manager.forward_to_thread(
        &bot,
        thread_id,
        &db_user,
        &msg,
        None,
    ).await {
        Ok(_) => {
            info!("消息已转发到话题 {}", thread_id);
        }
        Err(e) => {
            warn!("转发消息失败: {}", e);
            bot.send_message(chat_id, 
                "消息发送失败，请稍后再试。"
            ).await?;
        }
    }

    Ok(())
}

fn get_media_description(msg: &Message) -> Option<String> {
    if msg.photo().is_some() {
        Some("[图片]".to_string())
    } else if msg.video().is_some() {
        Some("[视频]".to_string())
    } else if msg.audio().is_some() {
        Some("[音频]".to_string())
    } else if msg.voice().is_some() {
        Some("[语音]".to_string())
    } else if msg.document().is_some() {
        Some("[文件]".to_string())
    } else if msg.sticker().is_some() {
        Some("[贴纸]".to_string())
    } else if msg.animation().is_some() {
        Some("[动画]".to_string())
    } else if msg.location().is_some() {
        Some("[位置]".to_string())
    } else if msg.contact().is_some() {
        Some("[联系人]".to_string())
    } else {
        None
    }
}
