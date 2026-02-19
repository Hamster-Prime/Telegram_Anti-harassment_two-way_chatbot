use dashmap::DashMap;
use std::sync::Arc;
use std::time::{Duration, Instant};

#[derive(Clone)]
pub struct RateLimiter {
    limits: Arc<DashMap<i64, Vec<Instant>>>,
    max_requests: usize,
    window: Duration,
}

impl RateLimiter {
    pub fn new(max_requests_per_minute: i32) -> Self {
        Self {
            limits: Arc::new(DashMap::new()),
            max_requests: max_requests_per_minute as usize,
            window: Duration::from_secs(60),
        }
    }

    /// 检查用户是否超过速率限制
    pub fn check_rate_limit(&self,
        user_id: i64,
    ) -> bool {
        let now = Instant::now();

        let mut entry = self.limits.entry(user_id).or_insert_with(Vec::new);

        // 清理过期记录
        entry.retain(|time| now.duration_since(*time) < self.window);

        if entry.len() >= self.max_requests {
            return false; // 超过限制
        }

        entry.push(now);
        true
    }

    /// 获取用户当前请求次数
    pub fn get_request_count(&self,
        user_id: i64,
    ) -> usize {
        let now = Instant::now();

        if let mut entry = self.limits.get_mut(&user_id) {
            entry.retain(|time| now.duration_since(*time) < self.window);
            return entry.len();
        }

        0
    }

    /// 清理所有过期记录
    pub fn cleanup(&self) {
        let now = Instant::now();

        self.limits.retain(|_, times| {
            times.retain(|time| now.duration_since(*time) < self.window);
            !times.is_empty()
        });
    }
}
