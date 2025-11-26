import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    BOT_TOKEN = os.getenv('BOT_TOKEN')
    BOT_ID = None
    BOT_USERNAME = None
    FORUM_GROUP_ID = int(os.getenv('FORUM_GROUP_ID') or 0)
    ADMIN_IDS = [int(id) for id in os.getenv('ADMIN_IDS', '').split(',') if id]
    
    GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
    ENABLE_AI_FILTER = os.getenv('ENABLE_AI_FILTER', 'true').lower() == 'true'
    AI_CONFIDENCE_THRESHOLD = int(os.getenv('AI_CONFIDENCE_THRESHOLD', '70'))
    
    VERIFICATION_ENABLED = os.getenv('VERIFICATION_ENABLED', 'true').lower() == 'true'
    AUTO_UNBLOCK_ENABLED = os.getenv('AUTO_UNBLOCK_ENABLED', 'true').lower() == 'true'
    
    DATABASE_PATH = os.getenv('DATABASE_PATH', './data/bot.db')
    
    MAX_WORKERS = int(os.getenv('MAX_WORKERS', '5'))
    QUEUE_TIMEOUT = int(os.getenv('QUEUE_TIMEOUT', '30'))
    
    VERIFICATION_TIMEOUT = int(os.getenv('VERIFICATION_TIMEOUT', '300'))
    MAX_VERIFICATION_ATTEMPTS = int(os.getenv('MAX_VERIFICATION_ATTEMPTS', '3'))
    
    MAX_MESSAGES_PER_MINUTE = int(os.getenv('MAX_MESSAGES_PER_MINUTE', '30'))

    RSS_ENABLED = os.getenv('RSS_ENABLED', 'false').lower() == 'true'
    RSS_DATA_FILE = os.getenv('RSS_DATA_FILE', './data/rss_subscriptions.json')
    RSS_CHECK_INTERVAL = int(os.getenv('RSS_CHECK_INTERVAL', '300'))
    RSS_AUTHORIZED_USER_IDS = [
        int(user_id) for user_id in os.getenv('RSS_AUTHORIZED_USER_IDS', '').split(',') if user_id
    ]
    
    @classmethod
    def validate(cls):
        if not cls.BOT_TOKEN:
            raise ValueError("BOT_TOKEN未设置")
        if not cls.FORUM_GROUP_ID or not cls.ADMIN_IDS:
            print("警告: FORUM_GROUP_ID 或 ADMIN_IDS 未设置。只有 /getid 功能可用。")

config = Config()
