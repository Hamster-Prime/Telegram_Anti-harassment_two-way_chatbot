use anyhow::Result;
use chrono::{DateTime, Utc};
use sqlx::{sqlite::SqlitePoolOptions, Pool, Sqlite};
use std::sync::Arc;

use crate::models::*;

#[derive(Clone)]
pub struct Database {
    pool: Arc<Pool<Sqlite>>,
}

impl Database {
    pub async fn new(database_path: &str) -> Result<Self> {
        // 确保目录存在
        if let Some(parent) = std::path::Path::new(database_path).parent() {
            tokio::fs::create_dir_all(parent).await?;
        }

        let pool = SqlitePoolOptions::new()
            .max_connections(5)
            .connect(&format!("sqlite:{}", database_path))
            .await?;

        Ok(Self {
            pool: Arc::new(pool),
        })
    }

    pub async fn initialize(&self) -> Result<()> {
        let migrations = vec![
            // 用户表
            r#"
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT NOT NULL,
                last_name TEXT,
                is_verified BOOLEAN DEFAULT FALSE,
                is_blocked BOOLEAN DEFAULT FALSE,
                is_exempt BOOLEAN DEFAULT FALSE,
                exempt_until TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            "#,
            // 话题表
            r#"
            CREATE TABLE IF NOT EXISTS threads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL UNIQUE,
                thread_id INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
            "#,
            // 消息表
            r#"
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                message_id INTEGER NOT NULL,
                thread_message_id INTEGER,
                content TEXT,
                media_type TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
            "#,
            // 黑名单表
            r#"
            CREATE TABLE IF NOT EXISTS blacklist (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                reason TEXT,
                blocked_by INTEGER NOT NULL,
                blocked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                auto_unblock_at TIMESTAMP,
                is_active BOOLEAN DEFAULT TRUE
            )
            "#,
            // 验证会话表
            r#"
            CREATE TABLE IF NOT EXISTS verification_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL UNIQUE,
                question TEXT NOT NULL,
                expected_answer TEXT NOT NULL,
                attempts INTEGER DEFAULT 0,
                max_attempts INTEGER DEFAULT 3,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP NOT NULL,
                is_completed BOOLEAN DEFAULT FALSE
            )
            "#,
            // 知识库表
            r#"
            CREATE TABLE IF NOT EXISTS knowledge_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                keyword TEXT NOT NULL UNIQUE,
                response TEXT NOT NULL,
                created_by INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            "#,
            // RSS订阅表
            r#"
            CREATE TABLE IF NOT EXISTS rss_subscriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                url TEXT NOT NULL,
                keywords TEXT,
                footer TEXT,
                last_checked TIMESTAMP,
                last_entry_date TIMESTAMP,
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, url)
            )
            "#,
            // 统计表
            r#"
            CREATE TABLE IF NOT EXISTS bot_stats (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                total_messages INTEGER DEFAULT 0,
                total_users INTEGER DEFAULT 0,
                total_threads INTEGER DEFAULT 0,
                blocked_count INTEGER DEFAULT 0,
                verified_count INTEGER DEFAULT 0,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            "#,
            // 插入初始统计记录
            r#"
            INSERT OR IGNORE INTO bot_stats (id) VALUES (1)
            "#,
            // 索引
            r#"
            CREATE INDEX IF NOT EXISTS idx_messages_user_id ON messages(user_id)
            "#,
            r#"
            CREATE INDEX IF NOT EXISTS idx_blacklist_user_id ON blacklist(user_id)
            "#,
            r#"
            CREATE INDEX IF NOT EXISTS idx_threads_user_id ON threads(user_id)
            "#,
        ];

        for migration in migrations {
            sqlx::query(migration).execute(&*self.pool).await?;
        }

        Ok(())
    }

    // 用户相关操作
    pub async fn get_or_create_user(
        &self,
        id: i64,
        username: Option<String>,
        first_name: String,
        last_name: Option<String>,
    ) -> Result<User> {
        let user: Option<User> = sqlx::query_as(
            r#"
            SELECT * FROM users WHERE id = ?
            "#,
        )
        .bind(id)
        .fetch_optional(&*self.pool)
        .await?;

        if let Some(user) = user {
            // 更新最后活动时间
            sqlx::query(
                r#"
                UPDATE users SET last_activity = CURRENT_TIMESTAMP WHERE id = ?
                "#,
            )
            .bind(id)
            .execute(&*self.pool)
            .await?;
            return Ok(user);
        }

        // 创建新用户
        sqlx::query(
            r#"
            INSERT INTO users (id, username, first_name, last_name)
            VALUES (?, ?, ?, ?)
            "#,
        )
        .bind(id)
        .bind(&username)
        .bind(&first_name)
        .bind(&last_name)
        .execute(&*self.pool)
        .await?;

        // 更新统计
        sqlx::query(
            r#"
            UPDATE bot_stats SET total_users = total_users + 1, updated_at = CURRENT_TIMESTAMP
            "#,
        )
        .execute(&*self.pool)
        .await?;

        Ok(User {
            id,
            username,
            first_name,
            last_name,
            is_verified: false,
            is_blocked: false,
            is_exempt: false,
            exempt_until: None,
            created_at: Utc::now(),
            last_activity: Utc::now(),
        })
    }

    pub async fn get_user(&self, id: i64) -> Result<Option<User>> {
        let user: Option<User> = sqlx::query_as(
            r#"
            SELECT * FROM users WHERE id = ?
            "#,
        )
        .bind(id)
        .fetch_optional(&*self.pool)
        .await?;

        Ok(user)
    }

    pub async fn set_user_verified(&self, user_id: i64, verified: bool) -> Result<()> {
        sqlx::query(
            r#"
            UPDATE users SET is_verified = ? WHERE id = ?
            "#,
        )
        .bind(verified)
        .bind(user_id)
        .execute(&*self.pool)
        .await?;

        if verified {
            sqlx::query(
                r#"
                UPDATE bot_stats SET verified_count = verified_count + 1 WHERE id = 1
                "#,
            )
            .execute(&*self.pool)
            .await?;
        }

        Ok(())
    }

    pub async fn set_user_blocked(&self, user_id: i64, blocked: bool) -> Result<()> {
        sqlx::query(
            r#"
            UPDATE users SET is_blocked = ? WHERE id = ?
            "#,
        )
        .bind(blocked)
        .bind(user_id)
        .execute(&*self.pool)
        .await?;
        Ok(())
    }

    pub async fn set_user_exempt(
        &self,
        user_id: i64,
        exempt: bool,
        hours: Option<i64>,
    ) -> Result<()> {
        let exempt_until = hours.map(|h| Utc::now() + chrono::Duration::hours(h));

        sqlx::query(
            r#"
            UPDATE users SET is_exempt = ?, exempt_until = ? WHERE id = ?
            "#,
        )
        .bind(exempt)
        .bind(exempt_until)
        .bind(user_id)
        .execute(&*self.pool)
        .await?;
        Ok(())
    }

    // 话题相关操作
    pub async fn get_thread(&self, user_id: i64) -> Result<Option<Thread>> {
        let thread: Option<Thread> = sqlx::query_as(
            r#"
            SELECT * FROM threads WHERE user_id = ?
            "#,
        )
        .bind(user_id)
        .fetch_optional(&*self.pool)
        .await?;

        Ok(thread)
    }

    pub async fn create_thread(&self, user_id: i64, thread_id: i32) -> Result<Thread> {
        sqlx::query(
            r#"
            INSERT OR REPLACE INTO threads (user_id, thread_id)
            VALUES (?, ?)
            "#,
        )
        .bind(user_id)
        .bind(thread_id)
        .execute(&*self.pool)
        .await?;

        // 更新统计
        sqlx::query(
            r#"
            UPDATE bot_stats SET total_threads = total_threads + 1 WHERE id = 1
            "#,
        )
        .execute(&*self.pool)
        .await?;

        Ok(Thread {
            id: 0, // 会被数据库填充
            user_id,
            thread_id,
            created_at: Utc::now(),
        })
    }

    pub async fn get_user_by_thread(&self, thread_id: i32) -> Result<Option<i64>> {
        let result: Option<(i64,)> = sqlx::query_as(
            r#"
            SELECT user_id FROM threads WHERE thread_id = ?
            "#,
        )
        .bind(thread_id)
        .fetch_optional(&*self.pool)
        .await?;

        Ok(result.map(|r| r.0))
    }

    // 消息相关
    pub async fn save_message(
        &self,
        user_id: i64,
        message_id: i32,
        thread_message_id: Option<i32>,
        content: Option<String>,
        media_type: Option<String>,
    ) -> Result<()> {
        sqlx::query(
            r#"
            INSERT INTO messages (user_id, message_id, thread_message_id, content, media_type)
            VALUES (?, ?, ?, ?, ?)
            "#,
        )
        .bind(user_id)
        .bind(message_id)
        .bind(thread_message_id)
        .bind(content)
        .bind(media_type)
        .execute(&*self.pool)
        .await?;

        // 更新统计
        sqlx::query(
            r#"
            UPDATE bot_stats SET total_messages = total_messages + 1, updated_at = CURRENT_TIMESTAMP WHERE id = 1
            "#,
        )
        .execute(&*self.pool)
        .await?;

        Ok(())
    }

    // 黑名单操作
    pub async fn add_to_blacklist(
        &self,
        user_id: i64,
        reason: Option<String>,
        blocked_by: i64,
        auto_unblock_hours: Option<i64>,
    ) -> Result<()> {
        let auto_unblock_at = auto_unblock_hours
            .map(|h| Utc::now() + chrono::Duration::hours(h));

        sqlx::query(
            r#"
            INSERT INTO blacklist (user_id, reason, blocked_by, auto_unblock_at, is_active)
            VALUES (?, ?, ?, ?, TRUE)
            "#,
        )
        .bind(user_id)
        .bind(reason)
        .bind(blocked_by)
        .bind(auto_unblock_at)
        .execute(&*self.pool)
        .await?;

        // 更新用户状态
        self.set_user_blocked(user_id, true).await?;

        // 更新统计
        sqlx::query(
            r#"
            UPDATE bot_stats SET blocked_count = blocked_count + 1 WHERE id = 1
            "#,
        )
        .execute(&*self.pool)
        .await?;

        Ok(())
    }

    pub async fn remove_from_blacklist(&self, user_id: i64) -> Result<()> {
        sqlx::query(
            r#"
            UPDATE blacklist SET is_active = FALSE WHERE user_id = ? AND is_active = TRUE
            "#,
        )
        .bind(user_id)
        .execute(&*self.pool)
        .await?;

        self.set_user_blocked(user_id, false).await?;
        Ok(())
    }

    pub async fn is_blacklisted(&self, user_id: i64) -> Result<bool> {
        let count: i64 = sqlx::query_scalar(
            r#"
            SELECT COUNT(*) FROM blacklist WHERE user_id = ? AND is_active = TRUE
            "#,
        )
        .bind(user_id)
        .fetch_one(&*self.pool)
        .await?;

        Ok(count > 0)
    }

    pub async fn get_blacklist(&self) -> Result<Vec<BlacklistEntry>> {
        let entries: Vec<BlacklistEntry> = sqlx::query_as(
            r#"
            SELECT * FROM blacklist WHERE is_active = TRUE ORDER BY blocked_at DESC
            "#,
        )
        .fetch_all(&*self.pool)
        .await?;

        Ok(entries)
    }

    // 验证会话操作
    pub async fn create_verification_session(
        &self,
        user_id: i64,
        question: String,
        expected_answer: String,
        max_attempts: i32,
        timeout_seconds: i64,
    ) -> Result<VerificationSession> {
        let expires_at = Utc::now() + chrono::Duration::seconds(timeout_seconds);

        sqlx::query(
            r#"
            INSERT OR REPLACE INTO verification_sessions 
            (user_id, question, expected_answer, max_attempts, expires_at, is_completed)
            VALUES (?, ?, ?, ?, ?, FALSE)
            "#,
        )
        .bind(user_id)
        .bind(&question)
        .bind(&expected_answer)
        .bind(max_attempts)
        .bind(expires_at)
        .execute(&*self.pool)
        .await?;

        Ok(VerificationSession {
            id: 0,
            user_id,
            question,
            expected_answer,
            attempts: 0,
            max_attempts,
            created_at: Utc::now(),
            expires_at,
            is_completed: false,
        })
    }

    pub async fn get_verification_session(
        &self,
        user_id: i64,
    ) -> Result<Option<VerificationSession>> {
        let session: Option<VerificationSession> = sqlx::query_as(
            r#"
            SELECT * FROM verification_sessions 
            WHERE user_id = ? AND is_completed = FALSE
            "#,
        )
        .bind(user_id)
        .fetch_optional(&*self.pool)
        .await?;

        Ok(session)
    }

    pub async fn increment_verification_attempt(&self,
        user_id: i64,
    ) -> Result<()> {
        sqlx::query(
            r#"
            UPDATE verification_sessions 
            SET attempts = attempts + 1
            WHERE user_id = ? AND is_completed = FALSE
            "#,
        )
        .bind(user_id)
        .execute(&*self.pool)
        .await?;
        Ok(())
    }

    pub async fn complete_verification(&self, user_id: i64, success: bool) -> Result<()> {
        sqlx::query(
            r#"
            UPDATE verification_sessions 
            SET is_completed = TRUE
            WHERE user_id = ? AND is_completed = FALSE
            "#,
        )
        .bind(user_id)
        .execute(&*self.pool)
        .await?;

        if success {
            self.set_user_verified(user_id, true).await?;
        }

        Ok(())
    }

    pub async fn cleanup_expired_verifications(&self) -> Result<()> {
        sqlx::query(
            r#"
            DELETE FROM verification_sessions 
            WHERE expires_at < CURRENT_TIMESTAMP AND is_completed = FALSE
            "#,
        )
        .execute(&*self.pool)
        .await?;
        Ok(())
    }

    // 知识库操作
    pub async fn add_knowledge_entry(
        &self,
        keyword: String,
        response: String,
        created_by: i64,
    ) -> Result<()> {
        sqlx::query(
            r#"
            INSERT OR REPLACE INTO knowledge_entries (keyword, response, created_by, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            "#,
        )
        .bind(keyword)
        .bind(response)
        .bind(created_by)
        .execute(&*self.pool)
        .await?;
        Ok(())
    }

    pub async fn get_knowledge_entry(&self,
        keyword: &str,
    ) -> Result<Option<KnowledgeEntry>> {
        let entry: Option<KnowledgeEntry> = sqlx::query_as(
            r#"
            SELECT * FROM knowledge_entries WHERE keyword = ?
            "#,
        )
        .bind(keyword)
        .fetch_optional(&*self.pool)
        .await?;

        Ok(entry)
    }

    pub async fn search_knowledge_entries(
        &self,
        query: &str,
    ) -> Result<Vec<KnowledgeEntry>> {
        let pattern = format!("%{}%", query);
        let entries: Vec<KnowledgeEntry> = sqlx::query_as(
            r#"
            SELECT * FROM knowledge_entries 
            WHERE keyword LIKE ? OR response LIKE ?
            "#,
        )
        .bind(&pattern)
        .bind(&pattern)
        .fetch_all(&*self.pool)
        .await?;

        Ok(entries)
    }

    pub async fn list_knowledge_entries(&self) -> Result<Vec<KnowledgeEntry>> {
        let entries: Vec<KnowledgeEntry> = sqlx::query_as(
            r#"
            SELECT * FROM knowledge_entries ORDER BY keyword
            "#,
        )
        .fetch_all(&*self.pool)
        .await?;

        Ok(entries)
    }

    pub async fn delete_knowledge_entry(&self, keyword: &str) -> Result<bool> {
        let result = sqlx::query(
            r#"
            DELETE FROM knowledge_entries WHERE keyword = ?
            "#,
        )
        .bind(keyword)
        .execute(&*self.pool)
        .await?;

        Ok(result.rows_affected() > 0)
    }

    // RSS订阅操作
    pub async fn add_rss_subscription(
        &self,
        user_id: i64,
        url: String,
        keywords: Vec<String>,
        footer: Option<String>,
    ) -> Result<()> {
        let keywords_str = keywords.join(",");

        sqlx::query(
            r#"
            INSERT OR REPLACE INTO rss_subscriptions 
            (user_id, url, keywords, footer, is_active, last_checked)
            VALUES (?, ?, ?, ?, TRUE, CURRENT_TIMESTAMP)
            "#,
        )
        .bind(user_id)
        .bind(url)
        .bind(keywords_str)
        .bind(footer)
        .execute(&*self.pool)
        .await?;
        Ok(())
    }

    pub async fn get_rss_subscriptions(
        &self,
        user_id: i64,
    ) -> Result<Vec<RSSSubscription>> {
        let rows = sqlx::query(
            r#"
            SELECT * FROM rss_subscriptions WHERE user_id = ? AND is_active = TRUE
            "#,
        )
        .bind(user_id)
        .fetch_all(&*self.pool)
        .await?;

        let mut subscriptions = Vec::new();
        for row in rows {
            let keywords_str: String = row.get("keywords");
            let keywords: Vec<String> = if keywords_str.is_empty() {
                vec![]
            } else {
                keywords_str.split(',').map(|s| s.to_string()).collect()
            };

            subscriptions.push(RSSSubscription {
                id: row.get("id"),
                user_id: row.get("user_id"),
                url: row.get("url"),
                keywords,
                footer: row.get("footer"),
                last_checked: row.get("last_checked"),
                last_entry_date: row.get("last_entry_date"),
                is_active: row.get("is_active"),
                created_at: row.get("created_at"),
            });
        }

        Ok(subscriptions)
    }

    pub async fn get_all_active_rss_subscriptions(&self) -> Result<Vec<RSSSubscription>> {
        let rows = sqlx::query(
            r#"
            SELECT * FROM rss_subscriptions WHERE is_active = TRUE
            "#,
        )
        .fetch_all(&*self.pool)
        .await?;

        let mut subscriptions = Vec::new();
        for row in rows {
            let keywords_str: String = row.get("keywords");
            let keywords: Vec<String> = if keywords_str.is_empty() {
                vec![]
            } else {
                keywords_str.split(',').map(|s| s.to_string()).collect()
            };

            subscriptions.push(RSSSubscription {
                id: row.get("id"),
                user_id: row.get("user_id"),
                url: row.get("url"),
                keywords,
                footer: row.get("footer"),
                last_checked: row.get("last_checked"),
                last_entry_date: row.get("last_entry_date"),
                is_active: row.get("is_active"),
                created_at: row.get("created_at"),
            });
        }

        Ok(subscriptions)
    }

    pub async fn update_rss_last_checked(
        &self,
        subscription_id: i64,
        last_entry_date: DateTime<Utc>,
    ) -> Result<()> {
        sqlx::query(
            r#"
            UPDATE rss_subscriptions 
            SET last_checked = CURRENT_TIMESTAMP, last_entry_date = ?
            WHERE id = ?
            "#,
        )
        .bind(last_entry_date)
        .bind(subscription_id)
        .execute(&*self.pool)
        .await?;
        Ok(())
    }

    pub async fn delete_rss_subscription(
        &self, user_id: i64, url: &str) -> Result<bool> {
        let result = sqlx::query(
            r#"
            DELETE FROM rss_subscriptions WHERE user_id = ? AND url = ?
            "#,
        )
        .bind(user_id)
        .bind(url)
        .execute(&*self.pool)
        .await?;

        Ok(result.rows_affected() > 0)
    }

    // 统计数据
    pub async fn get_stats(&self) -> Result<BotStats> {
        let stats: BotStats = sqlx::query_as(
            r#"
            SELECT * FROM bot_stats WHERE id = 1
            "#,
        )
        .fetch_one(&*self.pool)
        .await?;

        Ok(stats)
    }
}
