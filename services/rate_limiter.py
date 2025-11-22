import asyncio
import time
from collections import defaultdict, deque
from config import config

class RateLimiter:
    def __init__(self):
        self.user_message_timestamps = defaultdict(lambda: deque())
        self.max_messages_per_minute = config.MAX_MESSAGES_PER_MINUTE
        self.user_warnings = {}
        self.lock = asyncio.Lock()
    
    async def check_user_rate_limit(self, user_id: int) -> tuple[bool, bool]:
        async with self.lock:
            now = time.time()
            timestamps = self.user_message_timestamps[user_id]
            while timestamps and timestamps[0] < now - 60.0:
                timestamps.popleft()
            is_over_limit = len(timestamps) >= self.max_messages_per_minute
            if is_over_limit:
                was_warned = self.user_warnings.get(user_id, False)
                return True, was_warned
            else:
                timestamps.append(now)
                if user_id in self.user_warnings:
                    del self.user_warnings[user_id]
                return False, False
    
    async def mark_user_warned(self, user_id: int):
        async with self.lock:
            self.user_warnings[user_id] = True
    
    async def clear_user_warning(self, user_id: int):
        async with self.lock:
            if user_id in self.user_warnings:
                del self.user_warnings[user_id]
            if user_id in self.user_message_timestamps:
                del self.user_message_timestamps[user_id]

rate_limiter = RateLimiter()
