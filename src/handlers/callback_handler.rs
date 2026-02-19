use teloxide::prelude::*;
use tracing::warn;

use crate::config::Config;
use crate::db::Database;
use std::sync::Arc;

pub async fn handle_callback(
    bot: Bot,
    q: CallbackQuery,
    config: Arc<Config>,
    db: Database,
) -> anyhow::Result<()> {
    let data = match q.data {
        Some(d) => d,
        None => return Ok(()),
    };

    let user = match q.from {
        Some(u) => u,
        None => return Ok(()),
    };

    // 检查管理员权限
    if !config.is_admin(user.id.0) {
        if let Some(msg) = q.message {
            bot.answer_callback_query(q.id)
                .text("无权操作")
                .await?;
        }
        return Ok(());
    }

    match data.as_str() {
        "blacklist" => {
            bot.answer_callback_query(q.id)
                .text("使用 /blacklist 查看黑名单")
                .await?;
        }
        "stats" => {
            bot.answer_callback_query(q.id)
                .text("使用 /stats 查看统计")
                .await?;
        }
        "autoreply_settings" => {
            bot.answer_callback_query(q.id)
                .text("使用 /autoreply 管理自动回复")
                .await?;
        }
        "autoreply_on" => {
            bot.answer_callback_query(q.id)
                .text("自动回复已开启")
                .await?;
        }
        "autoreply_off" => {
            bot.answer_callback_query(q.id)
                .text("自动回复已关闭")
                .await?;
        }
        "autoreply_add" => {
            bot.answer_callback_query(q.id)
                .text("使用 /autoreply add [关键词] [回复] 添加条目")
                .await?;
        }
        "autoreply_list" => {
            bot.answer_callback_query(q.id)
                .text("使用 /autoreply list 查看知识库")
                .await?;
        }
        "rss_manage" => {
            bot.answer_callback_query(q.id)
                .text("使用 /rss 管理订阅")
                .await?;
        }
        _ => {
            bot.answer_callback_query(q.id)
                .text("未知操作")
                .await?;
        }
    }

    Ok(())
}
