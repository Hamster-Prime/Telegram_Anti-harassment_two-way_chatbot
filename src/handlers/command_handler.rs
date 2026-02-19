use teloxide::macros::BotCommands;
use teloxide::types::ParseMode;
use teloxide::prelude::*;

use crate::config::Config;
use crate::db::Database;
use crate::services::{NetworkTestService, ThreadManager, BlacklistService, VerificationService, AIService};
use std::sync::Arc;

#[derive(BotCommands, Clone)]
#[command(rename_rule = "lowercase", description = "可用命令:")]
pub enum Command {
    #[command(description = "启动机器人")]
    Start,
    #[command(description = "显示帮助信息")]
    Help,
    #[command(description = "获取当前聊天ID")]
    GetId,
    #[command(description = "打开管理面板 (管理员)")]
    Panel,
    #[command(description = "拉黑当前话题用户 (管理员)")]
    Block,
    #[command(description = "解封用户 (管理员)")]
    Unblock(String),
    #[command(description = "查看黑名单 (管理员)")]
    Blacklist,
    #[command(description = "查看统计信息 (管理员)")]
    Stats,
    #[command(description = "设置内容审查豁免 (管理员) - 用法: /exempt [permanent|temp 小时] [原因]")]
    Exempt(String),
    #[command(description = "自动回复管理 (管理员)")]
    AutoReply(String),
    #[command(description = "RSS订阅管理 - 用法: /rss [add|remove|list] [URL]")]
    Rss(String),
    #[command(description = "Ping测试 - 用法: /ping [目标]")]
    Ping(String),
    #[command(description = "路由追踪 - 用法: /traceroute [目标]")]
    Traceroute(String),
}

pub async fn start(
    bot: Bot,
    msg: Message,
) -> anyhow::Result<()> {
    let welcome_text = format!(
        "欢迎使用双向聊天机器人！\n\n" \
        "这是一个功能完善的 Telegram 双向聊天机器人，支持:\n" \
        "• AI 智能内容过滤\n" \
        "• 人机验证系统\n" \
        "• 黑名单管理\n" \
        "• RSS 订阅推送\n" \
        "• 网络测试工具\n\n" \
        "使用 /help 查看详细帮助。"
    );

    bot.send_message(msg.chat.id, welcome_text).await?;
    Ok(())
}

pub async fn help(
    bot: Bot,
    msg: Message,
    config: Arc<Config>,
) -> anyhow::Result<()> {
    let is_admin = msg.from()
        .map(|u| config.is_admin(u.id.0))
        .unwrap_or(false);

    let mut help_text = String::from(
        "**用户命令:**\n" \
        "/start - 启动机器人\n" \
        "/help - 显示此帮助\n" \
        "/getid - 获取当前聊天ID\n\n"
    );

    if is_admin {
        help_text.push_str(
            "**管理员命令:**\n" \
            "/panel - 打开管理面板\n" \
            "/block - 拉黑当前话题用户\n" \
            "/unblock [用户ID] - 解封用户\n" \
            "/blacklist - 查看黑名单\n" \
            "/stats - 查看统计信息\n" \
            "/exempt [permanent|temp 小时] [原因] - 设置内容审查豁免\n" \
            "/autoreply [on|off|add|edit|delete|list] - 管理自动回复\n" \
            "/rss [add|remove|list] [URL] - RSS订阅管理\n" \
            "/ping [目标] - 网络Ping测试\n" \
            "/traceroute [目标] - 路由追踪\n"
        );
    }

    bot.send_message(msg.chat.id, help_text)
        .parse_mode(ParseMode::Markdown)
        .await?;

    Ok(())
}

pub async fn get_id(
    bot: Bot,
    msg: Message,
) -> anyhow::Result<()> {
    let chat_id = msg.chat.id.0;
    let user_id = msg.from().map(|u| u.id.0);

    let mut text = format!("当前聊天 ID: `{}`", chat_id);
    
    if let Some(uid) = user_id {
        text.push_str(&format!("\n你的用户 ID: `{}`", uid));
    }

    if let Some(thread_id) = msg.thread_id {
        text.push_str(&format!("\n话题 ID: `{}`", thread_id));
    }

    bot.send_message(msg.chat.id, text)
        .parse_mode(ParseMode::MarkdownV2)
        .await?;

    Ok(())
}

pub async fn panel(
    bot: Bot,
    msg: Message,
    config: Arc<Config>,
) -> anyhow::Result<()> {
    let user = msg.from().context("无法获取用户信息")?;
    
    if !config.is_admin(user.id.0) {
        bot.send_message(msg.chat.id, "无权访问").await?;
        return Ok(());
    }

    let keyboard = teloxide::types::InlineKeyboardMarkup::new(vec![
        vec![
            teloxide::types::InlineKeyboardButton::callback("查看黑名单", "blacklist"),
            teloxide::types::InlineKeyboardButton::callback("查看统计", "stats"),
        ],
        vec![
            teloxide::types::InlineKeyboardButton::callback("自动回复设置", "autoreply_settings"),
            teloxide::types::InlineKeyboardButton::callback("RSS管理", "rss_manage"),
        ],
    ]);

    bot.send_message(msg.chat.id, "**管理面板**")
        .parse_mode(ParseMode::Markdown)
        .reply_markup(keyboard)
        .await?;

    Ok(())
}

pub async fn block(
    bot: Bot,
    msg: Message,
    config: Arc<Config>,
    db: Database,
) -> anyhow::Result<()> {
    let user = msg.from().context("无法获取用户信息")?;
    
    if !config.is_admin(user.id.0) {
        bot.send_message(msg.chat.id, "无权执行此操作").await?;
        return Ok(());
    }

    // 从话题ID获取用户ID
    let Some(thread_id) = msg.thread_id else {
        bot.send_message(msg.chat.id, "请在用户话题中使用此命令").await?;
        return Ok(());
    };

    let target_user_id = match db.get_user_by_thread(thread_id).await? {
        Some(id) => id,
        None => {
            bot.send_message(msg.chat.id, "无法找到话题对应的用户").await?;
            return Ok(());
        }
    };

    let blacklist = BlacklistService::new(db, config);
    blacklist.block_user(target_user_id, Some("管理员操作".to_string()), user.id.0, None).await?;

    bot.send_message(msg.chat.id, format!("已拉黑用户 {}", target_user_id)).await?;
    Ok(())
}

pub async fn unblock(
    bot: Bot,
    msg: Message,
    config: Arc<Config>,
    db: Database,
    args: String,
) -> anyhow::Result<()> {
    let user = msg.from().context("无法获取用户信息")?;
    
    if !config.is_admin(user.id.0) {
        bot.send_message(msg.chat.id, "无权执行此操作").await?;
        return Ok(());
    }

    let target_id: i64 = args.trim().parse()
        .map_err(|_| anyhow::anyhow!("无效的用户ID"))?;

    let blacklist = BlacklistService::new(db, config);
    blacklist.unblock_user(target_id).await?;

    bot.send_message(msg.chat.id, format!("已解封用户 {}", target_id)).await?;
    Ok(())
}

pub async fn blacklist(
    bot: Bot,
    msg: Message,
    config: Arc<Config>,
    db: Database,
) -> anyhow::Result<()> {
    let user = msg.from().context("无法获取用户信息")?;
    
    if !config.is_admin(user.id.0) {
        bot.send_message(msg.chat.id, "无权访问").await?;
        return Ok(());
    }

    let blacklist = BlacklistService::new(db, config);
    let entries = blacklist.get_blacklist().await?;

    if entries.is_empty() {
        bot.send_message(msg.chat.id, "黑名单为空").await?;
        return Ok(());
    }

    let mut text = String::from("**当前黑名单:**\n\n");
    for entry in entries {
        text.push_str(&format!(
            "• 用户ID: `{}`\n  原因: {}\n  时间: {}\n\n",
            entry.user_id,
            entry.reason.as_deref().unwrap_or("无"),
            entry.blocked_at.format("%Y-%m-%d %H:%M")
        ));
    }

    bot.send_message(msg.chat.id, text)
        .parse_mode(ParseMode::MarkdownV2)
        .await?;

    Ok(())
}

pub async fn stats(
    bot: Bot,
    msg: Message,
    config: Arc<Config>,
    db: Database,
) -> anyhow::Result<()> {
    let user = msg.from().context("无法获取用户信息")?;
    
    if !config.is_admin(user.id.0) {
        bot.send_message(msg.chat.id, "无权访问").await?;
        return Ok(());
    }

    let stats = db.get_stats().await?;

    let text = format!(
        "**机器人统计信息**\n\n" \
        "总消息数: {}\n" \
        "总用户数: {}\n" \
        "总话题数: {}\n" \
        "拉黑用户数: {}\n" \
        "已验证用户数: {}\n" \
        "最后更新: {}",
        stats.total_messages,
        stats.total_users,
        stats.total_threads,
        stats.blocked_count,
        stats.verified_count,
        stats.updated_at.format("%Y-%m-%d %H:%M:%S")
    );

    bot.send_message(msg.chat.id, text)
        .parse_mode(ParseMode::Markdown)
        .await?;

    Ok(())
}

pub async fn exempt(
    bot: Bot,
    msg: Message,
    config: Arc<Config>,
    db: Database,
    args: String,
) -> anyhow::Result<()> {
    let user = msg.from().context("无法获取用户信息")?;
    
    if !config.is_admin(user.id.0) {
        bot.send_message(msg.chat.id, "无权执行此操作").await?;
        return Ok(());
    }

    let parts: Vec<&str> = args.trim().split_whitespace().collect();
    if parts.is_empty() {
        bot.send_message(msg.chat.id, 
            "用法: /exempt [permanent|temp 小时] [原因]\n或在话题中直接发送 /exempt"
        ).await?;
        return Ok(());
    }

    // 获取目标用户ID
    let target_user_id = if let Some(thread_id) = msg.thread_id {
        match db.get_user_by_thread(thread_id).await? {
            Some(id) => id,
            None => {
                bot.send_message(msg.chat.id, "无法找到话题对应的用户").await?;
                return Ok(());
            }
        }
    } else {
        // 从参数解析用户ID
        parts[0].parse()
            .map_err(|_| anyhow::anyhow!("请在话题中使用或指定用户ID"))?
    };

    let (exempt, hours) = match parts[0] {
        "permanent" | "永久" => (true, None),
        "temp" | "临时" => {
            let h = parts.get(1)
                .and_then(|s| s.parse().ok())
                .unwrap_or(24);
            (true, Some(h))
        }
        "remove" | "取消" => (false, None),
        _ => {
            bot.send_message(msg.chat.id, "无效的操作类型").await?;
            return Ok(());
        }
    };

    db.set_user_exempt(target_user_id, exempt, hours).await?;

    let msg_text = if exempt {
        if let Some(h) = hours {
            format!("已为用户 {} 设置临时豁免（{}小时）", target_user_id, h)
        } else {
            format!("已为用户 {} 设置永久豁免", target_user_id)
        }
    } else {
        format!("已取消用户 {} 的豁免", target_user_id)
    };

    bot.send_message(msg.chat.id, msg_text).await?;
    Ok(())
}

pub async fn auto_reply(
    bot: Bot,
    msg: Message,
    config: Arc<Config>,
    db: Database,
    args: String,
) -> anyhow::Result<()> {
    let user = msg.from().context("无法获取用户信息")?;
    
    if !config.is_admin(user.id.0) {
        bot.send_message(msg.chat.id, "无权执行此操作").await?;
        return Ok(());
    }

    let parts: Vec<&str> = args.trim().splitn(3, ' ').collect();
    
    if parts.is_empty() {
        // 显示自动回复菜单
        let keyboard = teloxide::types::InlineKeyboardMarkup::new(vec![
            vec![
                teloxide::types::InlineKeyboardButton::callback("开启自动回复", "autoreply_on"),
                teloxide::types::InlineKeyboardButton::callback("关闭自动回复", "autoreply_off"),
            ],
            vec![
                teloxide::types::InlineKeyboardButton::callback("添加知识条目", "autoreply_add"),
                teloxide::types::InlineKeyboardButton::callback("管理知识库", "autoreply_list"),
            ],
        ]);

        bot.send_message(msg.chat.id, "**自动回复管理**")
            .parse_mode(ParseMode::Markdown)
            .reply_markup(keyboard)
            .await?;
        return Ok(());
    }

    match parts[0] {
        "on" | "开启" => {
            bot.send_message(msg.chat.id, "自动回复已开启").await?;
        }
        "off" | "关闭" => {
            bot.send_message(msg.chat.id, "自动回复已关闭").await?;
        }
        "add" | "添加" => {
            if parts.len() < 3 {
                bot.send_message(msg.chat.id, "用法: /autoreply add [关键词] [回复内容]").await?;
                return Ok(());
            }
            db.add_knowledge_entry(parts[1].to_string(), parts[2].to_string(), user.id.0).await?;
            bot.send_message(msg.chat.id, format!("已添加知识条目: {}", parts[1])).await?;
        }
        "list" | "列表" => {
            let entries = db.list_knowledge_entries().await?;
            if entries.is_empty() {
                bot.send_message(msg.chat.id, "知识库为空").await?;
                return Ok(());
            }
            let mut text = String::from("**知识库条目:**\n\n");
            for entry in entries {
                text.push_str(&format!("• **{}**: {}\n", entry.keyword, entry.response));
            }
            bot.send_message(msg.chat.id, text)
                .parse_mode(ParseMode::Markdown)
                .await?;
        }
        "delete" | "删除" => {
            if parts.len() < 2 {
                bot.send_message(msg.chat.id, "用法: /autoreply delete [关键词]").await?;
                return Ok(());
            }
            if db.delete_knowledge_entry(parts[1]).await? {
                bot.send_message(msg.chat.id, format!("已删除: {}", parts[1])).await?;
            } else {
                bot.send_message(msg.chat.id, format!("未找到: {}", parts[1])).await?;
            }
        }
        _ => {
            bot.send_message(msg.chat.id, "未知命令").await?;
        }
    }

    Ok(())
}

pub async fn rss(
    bot: Bot,
    msg: Message,
    config: Arc<Config>,
    db: Database,
    args: String,
) -> anyhow::Result<()> {
    let user = msg.from().context("无法获取用户信息")?;
    
    // 检查RSS权限
    let authorized_ids = config.rss_authorized_ids();
    if !config.is_admin(user.id.0) && !authorized_ids.contains(&user.id.0) {
        bot.send_message(msg.chat.id, "无权使用RSS功能").await?;
        return Ok(());
    }

    let parts: Vec<&str> = args.trim().splitn(2, ' ').collect();
    
    if parts.is_empty() {
        bot.send_message(msg.chat.id, 
            "**RSS订阅管理**\n\n" \
            "/rss add [URL] - 添加订阅\n" \
            "/rss remove [URL] - 删除订阅\n" \
            "/rss list - 查看订阅列表\n" \
            "/rss keywords [URL] [关键词1,关键词2] - 设置关键词过滤\n" \
            "/rss footer [URL] [页脚文字] - 设置推送页脚"
        ).await?;
        return Ok(());
    }

    let rss_service = crate::services::RSSService::new(&config)?;

    match parts[0] {
        "add" => {
            if parts.len() < 2 {
                bot.send_message(msg.chat.id, "请提供RSS URL").await?;
                return Ok(());
            }
            let url = parts[1];
            match rss_service.add_subscription(&db, user.id.0, url.to_string(), vec![], None).await {
                Ok(_) => bot.send_message(msg.chat.id, "订阅添加成功").await?,
                Err(e) => bot.send_message(msg.chat.id, format!("添加失败: {}", e)).await?,
            }
        }
        "remove" => {
            if parts.len() < 2 {
                bot.send_message(msg.chat.id, "请提供RSS URL").await?;
                return Ok(());
            }
            let url = parts[1];
            if rss_service.remove_subscription(&db, user.id.0, url).await? {
                bot.send_message(msg.chat.id, "订阅已删除").await?;
            } else {
                bot.send_message(msg.chat.id, "未找到该订阅").await?;
            }
        }
        "list" => {
            let subs = rss_service.get_user_subscriptions(&db, user.id.0).await?;
            if subs.is_empty() {
                bot.send_message(msg.chat.id, "你没有RSS订阅").await?;
                return Ok(());
            }
            let mut text = String::from("**你的RSS订阅:**\n\n");
            for sub in subs {
                text.push_str(&format!("• {}\n", sub.url));
                if !sub.keywords.is_empty() {
                    text.push_str(&format!("  关键词: {}\n", sub.keywords.join(", ")));
                }
            }
            bot.send_message(msg.chat.id, text)
                .parse_mode(ParseMode::Markdown)
                .await?;
        }
        _ => {
            bot.send_message(msg.chat.id, "未知命令，使用 /rss 查看帮助").await?;
        }
    }

    Ok(())
}

pub async fn ping(
    bot: Bot,
    msg: Message,
    config: Arc<Config>,
    network: NetworkTestService,
    target: String,
) -> anyhow::Result<()> {
    if !config.network_test_enabled {
        bot.send_message(msg.chat.id, "网络测试功能未启用").await?;
        return Ok(());
    }

    let target = if target.trim().is_empty() {
        bot.send_message(msg.chat.id, "用法: /ping [目标地址]").await?;
        return Ok(());
    } else {
        target.trim()
    };

    bot.send_message(msg.chat.id, format!("正在Ping {}...", target)).await?;

    match network.ping(target, Some(4)).await {
        Ok(result) => {
            bot.send_message(msg.chat.id, result).await?;
        }
        Err(e) => {
            bot.send_message(msg.chat.id, format!("测试失败: {}", e)).await?;
        }
    }

    Ok(())
}

pub async fn traceroute(
    bot: Bot,
    msg: Message,
    config: Arc<Config>,
    network: NetworkTestService,
    target: String,
) -> anyhow::Result<()> {
    if !config.network_test_enabled {
        bot.send_message(msg.chat.id, "网络测试功能未启用").await?;
        return Ok(());
    }

    let target = if target.trim().is_empty() {
        bot.send_message(msg.chat.id, "用法: /traceroute [目标地址]").await?;
        return Ok(());
    } else {
        target.trim()
    };

    bot.send_message(msg.chat.id, format!("正在追踪路由到 {}...", target)).await?;

    match network.traceroute(target, false).await {
        Ok(result) => {
            // 结果可能很长，需要分段发送
            if result.len() > 4000 {
                for chunk in result.chars().collect::<Vec<_>>().chunks(4000) {
                    bot.send_message(msg.chat.id, chunk.iter().collect::<String>()).await?;
                }
            } else {
                bot.send_message(msg.chat.id, result).await?;
            }
        }
        Err(e) => {
            bot.send_message(msg.chat.id, format!("追踪失败: {}", e)).await?;
        }
    }

    Ok(())
}

use anyhow::Context;
