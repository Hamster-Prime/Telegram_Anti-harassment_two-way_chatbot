use anyhow::{Result, Context};
use serde::Deserialize;
use std::sync::Arc;

#[derive(Debug, Clone, Deserialize)]
pub struct Config {
    #[serde(rename = "BOT_TOKEN")]
    pub bot_token: String,

    #[serde(rename = "FORUM_GROUP_ID")]
    pub forum_group_id: i64,

    #[serde(rename = "ADMIN_IDS")]
    pub admin_ids: String,

    #[serde(rename = "GEMINI_API_KEY")]
    pub gemini_api_key: Option<String>,

    #[serde(rename = "GEMINI_MODEL")]
    pub gemini_model: String,

    #[serde(rename = "OPENAI_API_KEY")]
    pub openai_api_key: Option<String>,

    #[serde(rename = "OPENAI_BASE_URL")]
    pub openai_base_url: String,

    #[serde(rename = "OPENAI_MODEL")]
    pub openai_model: String,

    #[serde(rename = "ENABLE_AI_FILTER")]
    pub enable_ai_filter: bool,

    #[serde(rename = "AI_CONFIDENCE_THRESHOLD")]
    pub ai_confidence_threshold: i32,

    #[serde(rename = "VERIFICATION_ENABLED")]
    pub verification_enabled: bool,

    #[serde(rename = "AUTO_UNBLOCK_ENABLED")]
    pub auto_unblock_enabled: bool,

    #[serde(rename = "RSS_ENABLED")]
    pub rss_enabled: bool,

    #[serde(rename = "NETWORK_TEST_ENABLED")]
    pub network_test_enabled: bool,

    #[serde(rename = "DATABASE_PATH")]
    pub database_path: String,

    #[serde(rename = "MAX_WORKERS")]
    pub max_workers: usize,

    #[serde(rename = "QUEUE_TIMEOUT")]
    pub queue_timeout: i64,

    #[serde(rename = "VERIFICATION_TIMEOUT")]
    pub verification_timeout: i64,

    #[serde(rename = "MAX_VERIFICATION_ATTEMPTS")]
    pub max_verification_attempts: i32,

    #[serde(rename = "MAX_MESSAGES_PER_MINUTE")]
    pub max_messages_per_minute: i32,

    #[serde(rename = "RSS_DATA_FILE")]
    pub rss_data_file: String,

    #[serde(rename = "RSS_CHECK_INTERVAL")]
    pub rss_check_interval: i64,

    #[serde(rename = "RSS_AUTHORIZED_USER_IDS")]
    pub rss_authorized_user_ids: String,

    #[serde(rename = "REMOTE_SSH_HOST")]
    pub remote_ssh_host: Option<String>,

    #[serde(rename = "REMOTE_SSH_PORT")]
    pub remote_ssh_port: u16,

    #[serde(rename = "REMOTE_SSH_USER")]
    pub remote_ssh_user: Option<String>,

    #[serde(rename = "REMOTE_SSH_KEY_PATH")]
    pub remote_ssh_key_path: Option<String>,
}

impl Default for Config {
    fn default() -> Self {
        Self {
            bot_token: String::new(),
            forum_group_id: 0,
            admin_ids: String::new(),
            gemini_api_key: None,
            gemini_model: "gemini-pro".to_string(),
            openai_api_key: None,
            openai_base_url: "https://api.openai.com/v1".to_string(),
            openai_model: "gpt-3.5-turbo".to_string(),
            enable_ai_filter: true,
            ai_confidence_threshold: 70,
            verification_enabled: true,
            auto_unblock_enabled: true,
            rss_enabled: false,
            network_test_enabled: false,
            database_path: "./data/bot.db".to_string(),
            max_workers: 5,
            queue_timeout: 30,
            verification_timeout: 300,
            max_verification_attempts: 3,
            max_messages_per_minute: 30,
            rss_data_file: "./data/rss_subscriptions.json".to_string(),
            rss_check_interval: 300,
            rss_authorized_user_ids: String::new(),
            remote_ssh_host: None,
            remote_ssh_port: 22,
            remote_ssh_user: None,
            remote_ssh_key_path: None,
        }
    }
}

impl Config {
    pub fn load() -> Result<Arc<Self>> {
        dotenvy::dotenv().ok();

        let mut cfg = config::Config::builder()
            .add_source(config::Environment::default())
            .build()
            .context("无法加载配置")?;

        let config: Config = cfg.try_deserialize()
            .context("配置解析失败")?;

        Ok(Arc::new(config))
    }

    pub fn validate(&self) -> Result<()> {
        if self.bot_token.is_empty() {
            anyhow::bail!("BOT_TOKEN 未设置");
        }
        if self.forum_group_id == 0 {
            tracing::warn!("FORUM_GROUP_ID 未设置，只有 /getid 功能可用");
        }
        if self.admin_ids.is_empty() {
            tracing::warn!("ADMIN_IDS 未设置，管理功能不可用");
        }
        Ok(())
    }

    pub fn admin_ids_vec(&self) -> Vec<i64> {
        self.admin_ids
            .split(',')
            .filter_map(|s| s.trim().parse().ok())
            .collect()
    }

    pub fn is_admin(&self, user_id: i64) -> bool {
        self.admin_ids_vec().contains(&user_id)
    }

    pub fn rss_authorized_ids(&self) -> Vec<i64> {
        self.rss_authorized_user_ids
            .split(',')
            .filter_map(|s| s.trim().parse().ok())
            .collect()
    }
}
