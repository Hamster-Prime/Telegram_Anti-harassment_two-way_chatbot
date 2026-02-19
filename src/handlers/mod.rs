use teloxide::dispatching::{Dispatcher, HandlerExt, UpdateFilterExt};
use teloxide::dptree;
use teloxide::prelude::*;
use teloxide::types::Update;

mod admin_handler;
mod callback_handler;
mod command_handler;
mod user_handler;

use crate::config::Config;
use crate::db::Database;
use crate::services::AIService;
use crate::services::NetworkTestService;

pub fn setup_handlers() -> dptree::Handler<'dptree::DependencyMap, anyhow::Result<()>, dptree::di::Injectable<_, anyhow::Result<()>, _>> {
    let command_handler = teloxide::filter_command::<command_handler::Command, _>()
        .branch(dptree::case![command_handler::Command::Start].endpoint(command_handler::start))
        .branch(dptree::case![command_handler::Command::Help].endpoint(command_handler::help))
        .branch(dptree::case![command_handler::Command::GetId].endpoint(command_handler::get_id))
        .branch(dptree::case![command_handler::Command::Panel].endpoint(command_handler::panel))
        .branch(dptree::case![command_handler::Command::Block].endpoint(command_handler::block))
        .branch(dptree::case![command_handler::Command::Unblock].endpoint(command_handler::unblock))
        .branch(dptree::case![command_handler::Command::Blacklist].endpoint(command_handler::blacklist))
        .branch(dptree::case![command_handler::Command::Stats].endpoint(command_handler::stats))
        .branch(dptree::case![command_handler::Command::Exempt(args)].endpoint(command_handler::exempt))
        .branch(dptree::case![command_handler::Command::AutoReply(args)].endpoint(command_handler::auto_reply))
        .branch(dptree::case![command_handler::Command::Rss(args)].endpoint(command_handler::rss))
        .branch(dptree::case![command_handler::Command::Ping(target)].endpoint(command_handler::ping))
        .branch(dptree::case![command_handler::Command::Traceroute(target)].endpoint(command_handler::traceroute));

    let message_handler = Update::filter_message()
        .branch(command_handler)
        .branch(dptree::endpoint(message_router));

    let callback_handler = Update::filter_callback_query()
        .endpoint(callback_handler::handle_callback);

    dptree::entry()
        .branch(message_handler)
        .branch(callback_handler)
}

async fn message_router(
    bot: Bot,
    msg: Message,
    config: Arc<Config>,
    db: Database,
    ai_service: AIService,
    network_service: NetworkTestService,
) -> anyhow::Result<()> {
    // 检查是否是论坛群组的消息
    if let Some(thread_id) = msg.thread_id {
        // 管理员在话题中回复
        if msg.chat.id.0 == config.forum_group_id {
            return admin_handler::handle_thread_message(
                bot, msg, thread_id, config, db,
            ).await;
        }
    }

    // 用户私聊消息
    if msg.chat.is_private() {
        return user_handler::handle_private_message(
            bot, msg, config, db, ai_service,
        ).await;
    }

    Ok(())
}

use std::sync::Arc;
