use anyhow::{Result, Context};
use chrono::{DateTime, Utc};
use reqwest::Client;
use rss::Channel;
use std::sync::Arc;
use std::time::Duration;
use teloxide::prelude::*;
use tracing::{info, warn, error};

use crate::config::Config;
use crate::db::Database;
use crate::models::RSSSubscription;

pub struct RSSService {
    config: Arc<Config>,
    http_client: Client,
}

impl RSSService {
    pub fn new(config: &Arc<Config>) -> Result<Self> {
        let http_client = Client::builder()
            .timeout(Duration::from_secs(30))
            .build()
            .context("创建HTTP客户端失败")?;

        Ok(Self {
            config: config.clone(),
            http_client,
        })
    }

    /// 运行后台RSS检查任务
    pub async fn run_background_task(
        &self,
        bot: Bot,
        db: Database,
        config: Arc<Config>,
    ) -> Result<()> {
        let interval = Duration::from_secs(config.rss_check_interval as u64);

        info!("RSS后台任务启动，检查间隔: {}秒", config.rss_check_interval);

        loop {
            tokio::time::sleep(interval).await;

            if let Err(e) = self.check_all_feeds(&bot, &db).await {
                error!("RSS检查失败: {}", e);
            }
        }
    }

    /// 检查所有RSS订阅
    async fn check_all_feeds(
        &self,
        bot: &Bot,
        db: &Database,
    ) -> Result<()> {
        let subscriptions = db.get_all_active_rss_subscriptions().await?;

        for sub in subscriptions {
            match self.check_feed(&sub).await {
                Ok(new_entries) => {
                    for entry in new_entries {
                        if let Err(e) = self.send_entry(bot, &sub, &entry).await {
                            warn!("发送RSS条目失败: {}", e);
                        }
                    }

                    // 更新最后检查时间
                    if let Some(latest) = sub.last_entry_date {
                        let _ = db.update_rss_last_checked(sub.id, latest).await;
                    }
                }
                Err(e) => {
                    warn!("检查RSS订阅失败 {}: {}", sub.url, e);
                }
            }
        }

        Ok(())
    }

    /// 检查单个RSS源
    async fn check_feed(
        &self,
        subscription: &RSSSubscription,
    ) -> Result<Vec<RSSEntry>> {
        let response = self.http_client
            .get(&subscription.url)
            .send()
            .await
            .context("获取RSS源失败")?;

        let content = response.bytes().await?;
        let channel = Channel::read_from(&content[..])
            .context("解析RSS源失败")?;

        let mut new_entries = vec![];

        for item in channel.items() {
            let pub_date = item.pub_date()
                .and_then(|d| DateTime::parse_from_rfc2822(d).ok())
                .map(|d| d.with_timezone(&Utc));

            // 检查是否为新条目
            if let Some(last_date) = subscription.last_entry_date {
                if let Some(pub_date) = pub_date {
                    if pub_date <= last_date {
                        continue;
                    }
                }
            }

            // 检查关键词过滤
            let title = item.title().unwrap_or("无标题");
            let description = item.description().unwrap_or("");

            if !subscription.keywords.is_empty() {
                let content = format!("{} {}", title, description).to_lowercase();
                let has_keyword = subscription.keywords.iter()
                    .any(|k| content.contains(&k.to_lowercase()));

                if !has_keyword {
                    continue;
                }
            }

            new_entries.push(RSSEntry {
                title: title.to_string(),
                link: item.link().map(|s| s.to_string()),
                description: description.to_string(),
                pub_date,
            });
        }

        // 按日期排序，只保留最新的
        new_entries.sort_by(|a, b| b.pub_date.cmp(&a.pub_date));

        Ok(new_entries)
    }

    /// 发送RSS条目给用户
    async fn send_entry(
        &self,
        bot: &Bot,
        subscription: &RSSSubscription,
        entry: &RSSEntry,
    ) -> Result<()> {
        let mut text = format!("**{}**\n\n", entry.title);

        if !entry.description.is_empty() {
            // 截断过长的描述
            let desc = if entry.description.len() > 500 {
                format!("{}...", &entry.description[..500])
            } else {
                entry.description.clone()
            };
            text.push_str(&format!("{}\n\n", desc));
        }

        if let Some(link) = &entry.link {
            text.push_str(&format!("[查看原文]({})\n", link));
        }

        if let Some(footer) = &subscription.footer {
            text.push_str(&format!("\n{}", footer));
        }

        bot.send_message(ChatId(subscription.user_id), text)
            .parse_mode(teloxide::types::ParseMode::MarkdownV2)
            .await?;

        Ok(())
    }

    /// 添加RSS订阅
    pub async fn add_subscription(
        &self,
        db: &Database,
        user_id: i64,
        url: String,
        keywords: Vec<String>,
        footer: Option<String>,
    ) -> Result<()> {
        // 验证RSS源是否有效
        let response = self.http_client
            .get(&url)
            .send()
            .await
            .context("无法访问RSS源")?;

        let content = response.bytes().await?;
        let _channel = Channel::read_from(&content[..])
            .context("无效的RSS源")?;

        db.add_rss_subscription(user_id, url, keywords, footer).await?;

        Ok(())
    }

    /// 获取用户的所有订阅
    pub async fn get_user_subscriptions(
        &self,
        db: &Database,
        user_id: i64,
    ) -> Result<Vec<RSSSubscription>> {
        db.get_rss_subscriptions(user_id).await
    }

    /// 删除订阅
    pub async fn remove_subscription(
        &self,
        db: &Database,
        user_id: i64,
        url: &str,
    ) -> Result<bool> {
        db.delete_rss_subscription(user_id, url).await
    }
}

#[derive(Debug, Clone)]
struct RSSEntry {
    title: String,
    link: Option<String>,
    description: String,
    pub_date: Option<DateTime<Utc>>,
}
