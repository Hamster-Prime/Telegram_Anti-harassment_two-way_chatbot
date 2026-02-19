use anyhow::{Result, Context};
use std::sync::Arc;
use teloxide::prelude::*;
use teloxide::types::{ForumTopic, ParseMode};
use tracing::{info, warn};

use crate::config::Config;
use crate::db::Database;
use crate::models::User;

pub struct ThreadManager {
    db: Database,
    config: Arc<Config>,
}

impl ThreadManager {
    pub fn new(db: Database, config: Arc<Config>) -> Self {
        Self { db, config }
    }

    /// 获取或创建用户的话题
    pub async fn get_or_create_thread(
        &self,
        bot: &Bot,
        user: &User,
    ) -> Result<i32> {
        // 先检查是否已有话题
        if let Some(thread) = self.db.get_thread(user.id).await? {
            return Ok(thread.thread_id);
        }

        // 创建新话题
        let topic = self.create_forum_topic(bot, user).await?;
        let thread_id = topic.message_thread_id;

        // 保存到数据库
        self.db.create_thread(user.id, thread_id).await?;

        info!("为用户 {} 创建话题: {}", user.id, thread_id);

        Ok(thread_id)
    }

    /// 创建论坛话题
    async fn create_forum_topic(
        &self,
        bot: &Bot,
        user: &User,
    ) -> Result<ForumTopic> {
        let topic_name = if let Some(ref username) = user.username {
            format!("@{} ({}", username, user.id)
        } else {
            let name = format!("{} {}",
                user.first_name,
                user.last_name.as_deref().unwrap_or("")
            ).trim().to_string();
            format!("{} ({})", name, user.id)
        };

        // 截断话题名称（Telegram限制为128字符）
        let topic_name = if topic_name.len() > 128 {
            format!("{}...", &topic_name[..125])
        } else {
            topic_name
        };

        let topic = bot.create_forum_topic(
            ChatId(self.config.forum_group_id),
            &topic_name,
        )
        .await
        .context("创建论坛话题失败")?;

        // 发送用户信息到话题
        let user_info = format!(
            "新用户对话开始\n\n" \
            "ID: `{}`\n" \
            "姓名: {} {}\n" \
            "用户名: {}\n" \
            "验证状态: {}\n" \
            "豁免状态: {}",
            user.id,
            user.first_name,
            user.last_name.as_deref().unwrap_or(""),
            user.username.as_deref().map(|u| format!("@{}", u)).unwrap_or_else(|| "无".to_string()),
            if user.is_verified { "✅ 已验证" } else { "⏳ 未验证" },
            if user.is_exempt { "✅ 已豁免" } else { "❌ 未豁免" }
        );

        let _ = bot.send_message(
            ChatId(self.config.forum_group_id),
            user_info,
        )
        .message_thread_id(topic.message_thread_id)
        .parse_mode(ParseMode::MarkdownV2)
        .await;

        Ok(topic)
    }

    /// 通过话题ID获取用户ID
    pub async fn get_user_by_thread(
        &self,
        thread_id: i32,
    ) -> Result<Option<i64>> {
        self.db.get_user_by_thread(thread_id).await
    }

    /// 转发消息到话题
    pub async fn forward_to_thread(
        &self,
        bot: &Bot,
        thread_id: i32,
        user: &User,
        msg: &Message,
        quoted_text: Option<&str>,
    ) -> Result<Message> {
        let chat_id = ChatId(self.config.forum_group_id);

        // 先发送用户标识（如果是回复的话）
        let reply_to = if let Some(quote) = quoted_text {
            let header = format!("📨 回复 `{}` 的消息:", user.id);
            let quote_formatted = format!(
                "{}\n\n```\n{}\n```",
                header,
                quote.chars().take(200).collect::<String>()
            );

            let sent = bot.send_message(chat_id, quote_formatted)
                .message_thread_id(thread_id)
                .parse_mode(ParseMode::MarkdownV2)
                .await
                .ok();

            sent.map(|m| m.id)
        } else {
            None
        };

        // 转发实际消息
        let forwarded = bot.forward_message(
            chat_id,
            msg.chat.id,
            msg.id,
        )
        .message_thread_id(thread_id)
        .await
        .context("转发消息失败")?;

        // 保存消息映射
        self.db.save_message(
            user.id,
            msg.id.0,
            Some(forwarded.id.0),
            msg.text().map(|t| t.to_string()),
            None, // 简化处理
        ).await?;

        Ok(forwarded)
    }

    /// 发送文本消息到用户
    pub async fn send_to_user(
        &self,
        bot: &Bot,
        user_id: i64,
        text: &str,
        parse_mode: Option<ParseMode>,
    ) -> Result<Message> {
        let mut req = bot.send_message(ChatId(user_id), text);

        if let Some(mode) = parse_mode {
            req = req.parse_mode(mode);
        }

        let sent = req.await.context("发送消息失败")?;

        Ok(sent)
    }

    /// 从话题回复到用户
    pub async fn reply_from_thread(
        &self,
        bot: &Bot,
        thread_id: i32,
        text: &str,
        reply_to_message_id: Option<MessageId>,
    ) -> Result<Message> {
        let user_id = self.get_user_by_thread(thread_id).await?
            .context("无法找到话题对应的用户")?;

        let mut req = bot.send_message(ChatId(user_id), text);

        if let Some(msg_id) = reply_to_message_id {
            req = req.reply_to_message_id(msg_id);
        }

        let sent = req.await.context("发送回复失败")?;

        Ok(sent)
    }
}
