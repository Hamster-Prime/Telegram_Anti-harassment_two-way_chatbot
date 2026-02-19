use teloxide::prelude::*;
use teloxide::types::ParseMode;
use tracing::{info, warn};

use crate::config::Config;
use crate::db::Database;
use crate::services::ThreadManager;
use std::sync::Arc;

pub async fn handle_thread_message(
    bot: Bot,
    msg: Message,
    thread_id: i32,
    config: Arc<Config>,
    db: Database,
) -> anyhow::Result<()> {
    // 获取发送者
    let user = match msg.from() {
        Some(u) => u,
        None => return Ok(()),
    };

    // 检查是否是管理员
    if !config.is_admin(user.id.0) {
        return Ok(()); // 忽略非管理员消息
    }

    // 获取话题对应的用户
    let target_user_id = match db.get_user_by_thread(thread_id).await? {
        Some(id) => id,
        None => {
            bot.send_message(msg.chat.id, "无法找到此话题对应的用户")
                .message_thread_id(thread_id)
                .await?;
            return Ok(());
        }
    };

    // 处理回复
    if let Some(text) = msg.text() {
        // 转发给目标用户
        let thread_manager = ThreadManager::new(db.clone(), config.clone());

        // 处理引用回复
        let reply_to_id = msg.reply_to_message()
            .and_then(|m| m.forward_from_message_id());

        match thread_manager.reply_from_thread(
            &bot,
            thread_id,
            text,
            reply_to_id,
        ).await {
            Ok(_) => {
                info!("管理员回复已发送给用户 {}", target_user_id);

                // 在话题中显示已发送
                bot.send_message(
                    msg.chat.id,
                    format!("✅ 已回复给用户 `{}`", target_user_id)
                )
                .message_thread_id(thread_id)
                .parse_mode(ParseMode::MarkdownV2)
                .await?;
            }
            Err(e) => {
                warn!("发送回复失败: {}", e);
                bot.send_message(
                    msg.chat.id,
                    format!("❌ 发送失败: {}", e)
                )
                .message_thread_id(thread_id)
                .await?;
            }
        }
    }

    // 处理媒体回复
    if msg.photo().is_some() || msg.video().is_some() || 
       msg.document().is_some() || msg.audio().is_some() ||
       msg.voice().is_some() || msg.animation().is_some() {

        // 复制媒体到用户
        match bot.copy_message(
            ChatId(target_user_id),
            msg.chat.id,
            msg.id,
        ).await {
            Ok(_) => {
                info!("媒体已复制给用户 {}", target_user_id);
            }
            Err(e) => {
                warn!("复制媒体失败: {}", e);
                bot.send_message(
                    msg.chat.id,
                    format!("❌ 发送媒体失败: {}", e)
                )
                .message_thread_id(thread_id)
                .await?;
            }
        }
    }

    Ok(())
}
