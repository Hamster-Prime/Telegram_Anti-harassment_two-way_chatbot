use anyhow::Result;
use std::sync::Arc;

use crate::config::Config;
use crate::db::Database;
use crate::models::BlacklistEntry;

pub struct BlacklistService {
    db: Database,
    config: Arc<Config>,
}

impl BlacklistService {
    pub fn new(db: Database, config: Arc<Config>) -> Self {
        Self { db, config }
    }

    /// 将用户加入黑名单
    pub async fn block_user(
        &self,
        user_id: i64,
        reason: Option<String>,
        blocked_by: i64,
        auto_unblock_hours: Option<i64>,
    ) -> Result<()> {
        self.db.add_to_blacklist(user_id, reason, blocked_by, auto_unblock_hours).await?;
        Ok(())
    }

    /// 将用户从黑名单移除
    pub async fn unblock_user(&self,
        user_id: i64,
    ) -> Result<()> {
        self.db.remove_from_blacklist(user_id).await?;
        Ok(())
    }

    /// 检查用户是否在黑名单中
    pub async fn is_blacklisted(&self,
        user_id: i64,
    ) -> Result<bool> {
        self.db.is_blacklisted(user_id).await
    }

    /// 获取当前黑名单列表
    pub async fn get_blacklist(&self,
    ) -> Result<Vec<BlacklistEntry>> {
        self.db.get_blacklist().await
    }

    /// 处理自动解封（定期调用）
    pub async fn process_auto_unblocks(&self,
    ) -> Result<Vec<i64>> {
        if !self.config.auto_unblock_enabled {
            return Ok(vec![]);
        }

        let blacklist = self.db.get_blacklist().await?;
        let mut unblocked = vec![];

        for entry in blacklist {
            if let Some(unblock_at) = entry.auto_unblock_at {
                if chrono::Utc::now() >= unblock_at {
                    self.db.remove_from_blacklist(entry.user_id).await?;
                    unblocked.push(entry.user_id);
                }
            }
        }

        Ok(unblocked)
    }
}
