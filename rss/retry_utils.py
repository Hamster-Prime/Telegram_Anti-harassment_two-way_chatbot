import asyncio
import logging
from typing import Callable, Any, TypeVar
from telegram import error as tg_error

logger = logging.getLogger(__name__)

T = TypeVar("T")

DEFAULT_MAX_RETRIES = 3
DEFAULT_INITIAL_DELAY = 1.0
DEFAULT_MAX_DELAY = 60.0
DEFAULT_BACKOFF_FACTOR = 2.0


def is_retryable_error(exception: Exception) -> bool:
    if isinstance(exception, (tg_error.NetworkError, tg_error.TimedOut)):
        return True

    if isinstance(exception, tg_error.TelegramServerError):
        return True

    if isinstance(exception, tg_error.RetryAfter):
        return True

    if isinstance(exception, (ConnectionError, OSError)):
        return True

    if isinstance(exception, tg_error.TelegramError):
        return False

    return True


async def retry_telegram_api(
    func: Callable[..., Any],
    *args,
    max_retries: int = DEFAULT_MAX_RETRIES,
    initial_delay: float = DEFAULT_INITIAL_DELAY,
    max_delay: float = DEFAULT_MAX_DELAY,
    backoff_factor: float = DEFAULT_BACKOFF_FACTOR,
    **kwargs,
) -> Any:
    last_exception = None

    for attempt in range(max_retries + 1):
        try:
            return await func(*args, **kwargs)
        except Exception as exc:
            last_exception = exc

            if not is_retryable_error(exc):
                logger.error("遇到不可重试的错误: %s: %s", type(exc).__name__, exc)
                raise

            if attempt >= max_retries:
                logger.error(
                    "达到最大重试次数 (%s)，放弃重试。最后错误: %s: %s",
                    max_retries,
                    type(exc).__name__,
                    exc,
                )
                raise

            if isinstance(exc, tg_error.RetryAfter):
                delay = float(exc.retry_after)
                logger.warning(
                    "遇到限流错误，等待 %s 秒后重试 (尝试 %s/%s)",
                    delay,
                    attempt + 1,
                    max_retries,
                )
            else:
                delay = min(initial_delay * (backoff_factor ** attempt), max_delay)
                logger.warning(
                    "Telegram API 调用失败 (%s: %s)，%.2f 秒后重试 (尝试 %s/%s)",
                    type(exc).__name__,
                    exc,
                    delay,
                    attempt + 1,
                    max_retries,
                )

            await asyncio.sleep(delay)

    if last_exception:
        raise last_exception

