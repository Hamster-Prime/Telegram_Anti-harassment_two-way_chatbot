use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use sqlx::FromRow;

#[derive(Debug, Clone, FromRow)]
pub struct User {
    pub id: i64,
    pub username: Option<String>,
    pub first_name: String,
    pub last_name: Option<String>,
    pub is_verified: bool,
    pub is_blocked: bool,
    pub is_exempt: bool,
    pub exempt_until: Option<DateTime<Utc>>,
    pub created_at: DateTime<Utc>,
    pub last_activity: DateTime<Utc>,
}

#[derive(Debug, Clone, FromRow)]
pub struct Thread {
    pub id: i64,
    pub user_id: i64,
    pub thread_id: i32,
    pub created_at: DateTime<Utc>,
}

#[derive(Debug, Clone, FromRow)]
pub struct Message {
    pub id: i64,
    pub user_id: i64,
    pub message_id: i32,
    pub thread_message_id: Option<i32>,
    pub content: Option<String>,
    pub media_type: Option<String>,
    pub created_at: DateTime<Utc>,
}

#[derive(Debug, Clone, FromRow)]
pub struct BlacklistEntry {
    pub id: i64,
    pub user_id: i64,
    pub reason: Option<String>,
    pub blocked_by: i64,
    pub blocked_at: DateTime<Utc>,
    pub auto_unblock_at: Option<DateTime<Utc>>,
    pub is_active: bool,
}

#[derive(Debug, Clone, FromRow)]
pub struct VerificationSession {
    pub id: i64,
    pub user_id: i64,
    pub question: String,
    pub expected_answer: String,
    pub attempts: i32,
    pub max_attempts: i32,
    pub created_at: DateTime<Utc>,
    pub expires_at: DateTime<Utc>,
    pub is_completed: bool,
}

#[derive(Debug, Clone, FromRow)]
pub struct KnowledgeEntry {
    pub id: i64,
    pub keyword: String,
    pub response: String,
    pub created_by: i64,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
}

#[derive(Debug, Clone, FromRow)]
pub struct BotStats {
    pub id: i64,
    pub total_messages: i64,
    pub total_users: i64,
    pub total_threads: i64,
    pub blocked_count: i64,
    pub verified_count: i64,
    pub updated_at: DateTime<Utc>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RSSSubscription {
    pub id: i64,
    pub user_id: i64,
    pub url: String,
    pub keywords: Vec<String>,
    pub footer: Option<String>,
    pub last_checked: Option<DateTime<Utc>>,
    pub last_entry_date: Option<DateTime<Utc>>,
    pub is_active: bool,
    pub created_at: DateTime<Utc>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AutoReplyConfig {
    pub enabled: bool,
    pub use_knowledge_base: bool,
}

#[derive(Debug, Clone)]
pub enum MediaType {
    Photo,
    Video,
    Audio,
    Voice,
    Document,
    Sticker,
    Animation,
    VideoNote,
    Location,
    Contact,
    Unknown,
}

impl MediaType {
    pub fn as_str(&self) -> &'static str {
        match self {
            MediaType::Photo => "photo",
            MediaType::Video => "video",
            MediaType::Audio => "audio",
            MediaType::Voice => "voice",
            MediaType::Document => "document",
            MediaType::Sticker => "sticker",
            MediaType::Animation => "animation",
            MediaType::VideoNote => "video_note",
            MediaType::Location => "location",
            MediaType::Contact => "contact",
            MediaType::Unknown => "unknown",
        }
    }
}

#[derive(Debug, Clone)]
pub enum VerificationResult {
    Success,
    Failed(String),
    Expired,
    MaxAttemptsReached,
}

#[derive(Debug, Clone)]
pub struct ContentAnalysis {
    pub is_spam: bool,
    pub is_harassment: bool,
    pub confidence: i32,
    pub reason: Option<String>,
}
