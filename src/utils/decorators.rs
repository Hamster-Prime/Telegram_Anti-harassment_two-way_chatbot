use std::future::Future;
use std::pin::Pin;

/// 管理员权限检查装饰器
pub fn require_admin<T, F, Fut>(f: F) -> impl Fn(T, i64) -> Pin<Box<dyn Future<Output = bool> + Send>>
where
    F: Fn(T) -> Fut + Send + 'static,
    Fut: Future<Output = bool> + Send + 'static,
    T: Send + 'static,
{
    move |ctx, user_id| {
        Box::pin(async move {
            f(ctx).await
        })
    }
}
