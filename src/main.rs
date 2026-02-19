use anyhow::Result;
use teloxide::prelude::*;
use tracing::{info, error};

mod config;
mod db;
mod handlers;
mod models;
mod services;
mod utils;

use crate::config::Config;
use crate::db::Database;
use crate::services::{AIService, RSSService, NetworkTestService};

#[tokio::main]
async fn main() -> Result<()> {
    // 初始化日志
    tracing_subscriber::fmt()
        .with_env_filter(tracing_subscriber::EnvFilter::from_default_env())
        .init();

    info!("启动 Telegram 双向聊天机器人 (Rust版)...");

    // 加载配置
    let config = Config::load()?;
    config.validate()?;

    // 初始化数据库
    let db = Database::new(&config.database_path).await?;
    db.initialize().await?;
    info!("数据库初始化完成");

    // 初始化服务
    let ai_service = AIService::new(&config)?;
    let rss_service = RSSService::new(&config)?;
    let network_service = NetworkTestService::new(&config)?;

    // 创建Bot
    let bot = Bot::new(&config.bot_token);

    // 启动RSS后台任务
    if config.rss_enabled {
        let rss_bot = bot.clone();
        let rss_db = db.clone();
        let rss_config = config.clone();
        tokio::spawn(async move {
            if let Err(e) = rss_service.run_background_task(rss_bot, rss_db, rss_config).await {
                error!("RSS后台任务错误: {}", e);
            }
        });
    }

    // 设置处理器
    let handler = handlers::setup_handlers();

    // 运行Bot
    info!("Bot开始运行...");
    Dispatcher::builder(bot, handler)
        .dependencies(dptree::deps![
            config.clone(),
            db.clone(),
            ai_service,
            network_service
        ])
        .enable_ctrlc_handler()
        .build()
        .dispatch()
        .await;

    info!("Bot已停止");
    Ok(())
}
