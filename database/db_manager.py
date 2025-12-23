import aiosqlite
import os
import logging
from datetime import datetime

class DatabaseManager:
    _instance = None

    def __new__(cls, db_path='./data/bot.db'):
        if cls._instance is None:
            cls._instance = super(DatabaseManager, cls).__new__(cls)
            cls._instance.db_path = db_path
            cls._instance.ensure_data_directory()
        return cls._instance

    def ensure_data_directory(self):
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

    def get_connection(self):
        return aiosqlite.connect(self.db_path)

    async def initialize(self):
        async with self.get_connection() as db:
            await self.create_users_table(db)
            await self.create_messages_table(db)
            await self.create_blacklist_table(db)
            await self.create_admins_table(db)
            await self.create_verification_sessions_table(db)
            await self.create_settings_table(db)
            await self.create_statistics_table(db)
            await self.create_filtered_messages_table(db)
            await self.create_knowledge_base_table(db)
            await self.create_exemptions_table(db)
            await self.migrate_database(db)
            await db.commit()
        logging.info("数据库初始化完成。")

    async def create_users_table(self, db):
        await db.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT NOT NULL,
                last_name TEXT,
                language_code TEXT,
                is_verified INTEGER DEFAULT 0,
                is_blacklisted INTEGER DEFAULT 0,
                blacklist_strikes INTEGER DEFAULT 0 NOT NULL,
                thread_id INTEGER,
                verification_attempts INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                message_count INTEGER DEFAULT 0
            )
        ''')
        await db.execute('CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)')
        await db.execute('CREATE INDEX IF NOT EXISTS idx_users_verified ON users(is_verified)')
        await db.execute('CREATE INDEX IF NOT EXISTS idx_users_blacklisted ON users(is_blacklisted)')
        await db.execute('CREATE INDEX IF NOT EXISTS idx_users_thread ON users(thread_id)')

    async def create_messages_table(self, db):
        await db.execute('''
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                message_id INTEGER NOT NULL,
                thread_id INTEGER,
                content TEXT,
                media_type TEXT,
                media_file_id TEXT,
                direction TEXT NOT NULL,
                is_forwarded INTEGER DEFAULT 0,
                reply_to_message_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
            )
        ''')
        await db.execute('CREATE INDEX IF NOT EXISTS idx_messages_user ON messages(user_id)')
        await db.execute('CREATE INDEX IF NOT EXISTS idx_messages_thread ON messages(thread_id)')
        await db.execute('CREATE INDEX IF NOT EXISTS idx_messages_direction ON messages(direction)')
        await db.execute('CREATE INDEX IF NOT EXISTS idx_messages_created ON messages(created_at)')

    async def create_blacklist_table(self, db):
        await db.execute('''
            CREATE TABLE IF NOT EXISTS blacklist (
                user_id INTEGER PRIMARY KEY,
                reason TEXT NOT NULL,
                blocked_by INTEGER NOT NULL,
                blocked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                permanent INTEGER DEFAULT 0,
                unblock_question TEXT,
                unblock_answer TEXT,
                unblock_attempts INTEGER DEFAULT 0,
                last_unblock_attempt TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
            )
        ''')
        await db.execute('CREATE INDEX IF NOT EXISTS idx_blacklist_blocked_at ON blacklist(blocked_at)')

    async def create_admins_table(self, db):
        await db.execute('''
            CREATE TABLE IF NOT EXISTS admins (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                added_by INTEGER,
                is_active INTEGER DEFAULT 1,
                permissions TEXT DEFAULT 'all'
            )
        ''')
        await db.execute('CREATE INDEX IF NOT EXISTS idx_admins_active ON admins(is_active)')

    async def create_verification_sessions_table(self, db):
        await db.execute('''
            CREATE TABLE IF NOT EXISTS verification_sessions (
                user_id INTEGER PRIMARY KEY,
                question TEXT NOT NULL,
                answer TEXT NOT NULL,
                attempts INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
            )
        ''')
        await db.execute('CREATE INDEX IF NOT EXISTS idx_verification_expires ON verification_sessions(expires_at)')

    async def create_settings_table(self, db):
        await db.execute('''
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                description TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        default_settings = [
            ('bot_version', '1.0.0', '机器人当前版本'),
            ('welcome_message', '欢迎使用本机器人！', '新用户收到的欢迎消息'),
            ('verification_enabled', '1', '是否启用新用户验证 (1=是, 0=否)'),
            ('ai_filter_enabled', '1', '是否启用AI垃圾消息过滤 (1=是, 0=否)'),
            ('max_message_length', '4096', '允许接收的最大消息长度'),
            ('queue_max_size', '1000', '内部消息处理队列的最大容量'),
            ('ai_provider', 'gemini', '当前使用的AI提供商 (gemini, openai)'),
            
            ('gemini_model_filter', 'gemini-2.5-flash', 'Gemini 内容审查模型'),
            ('gemini_model_verification', 'gemini-2.5-flash-lite', 'Gemini 验证码生成模型'),
            ('gemini_model_autoreply', 'gemini-2.5-flash', 'Gemini 自动回复模型'),

            ('openai_model_filter', 'gpt-4.1', 'OpenAI 内容审查模型'),
            ('openai_model_verification', 'gpt-4.1-mini', 'OpenAI 验证码生成模型'),
            ('openai_model_autoreply', 'gpt-4.1', 'OpenAI 自动回复模型')
        ]
        for key, value, description in default_settings:
            await db.execute(
                'INSERT OR IGNORE INTO settings (key, value, description) VALUES (?, ?, ?)',
                (key, value, description)
            )

    async def create_statistics_table(self, db):
        await db.execute('''
            CREATE TABLE IF NOT EXISTS statistics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                stat_date DATE NOT NULL,
                total_users INTEGER DEFAULT 0,
                active_users INTEGER DEFAULT 0,
                messages_sent INTEGER DEFAULT 0,
                messages_received INTEGER DEFAULT 0,
                verifications_passed INTEGER DEFAULT 0,
                verifications_failed INTEGER DEFAULT 0,
                users_blocked INTEGER DEFAULT 0,
                users_unblocked INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(stat_date)
            )
        ''')
        await db.execute('CREATE INDEX IF NOT EXISTS idx_statistics_date ON statistics(stat_date)')

    async def create_filtered_messages_table(self, db):
        await db.execute('''
            CREATE TABLE IF NOT EXISTS filtered_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                message_id INTEGER NOT NULL,
                content TEXT,
                reason TEXT,
                media_type TEXT,
                media_file_id TEXT,
                filtered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
            )
        ''')
        await db.execute('CREATE INDEX IF NOT EXISTS idx_filtered_messages_user_id ON filtered_messages(user_id)')

    async def create_knowledge_base_table(self, db):
        await db.execute('''
            CREATE TABLE IF NOT EXISTS knowledge_base (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        await db.execute('CREATE INDEX IF NOT EXISTS idx_knowledge_base_title ON knowledge_base(title)')

    async def create_exemptions_table(self, db):
        await db.execute('''
            CREATE TABLE IF NOT EXISTS exemptions (
                user_id INTEGER PRIMARY KEY,
                is_permanent INTEGER DEFAULT 0,
                expires_at TIMESTAMP,
                exempted_by INTEGER NOT NULL,
                reason TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
            )
        ''')
        await db.execute('CREATE INDEX IF NOT EXISTS idx_exemptions_expires ON exemptions(expires_at)')
        await db.execute('CREATE INDEX IF NOT EXISTS idx_exemptions_permanent ON exemptions(is_permanent)')

    async def get_filtered_messages_by_user(self, user_id, limit=5):
        async with self.get_connection() as db:
            cursor = await db.execute(
                'SELECT content, reason FROM filtered_messages WHERE user_id = ? ORDER BY filtered_at DESC LIMIT ?',
                (user_id, limit)
            )
            rows = await cursor.fetchall()
            return [{"content": row[0], "reason": row[1]} for row in rows]

    async def migrate_database(self, db):
        try:
            await db.execute('ALTER TABLE users ADD COLUMN blacklist_strikes INTEGER DEFAULT 0 NOT NULL')
            logging.info("数据库迁移：成功为 'users' 表添加 'blacklist_strikes' 列。")
        except aiosqlite.OperationalError as e:
            if "duplicate column name" not in str(e):
                raise e

        try:
            await db.execute('ALTER TABLE blacklist ADD COLUMN permanent INTEGER DEFAULT 0')
            logging.info("数据库迁移：成功为 'blacklist' 表添加 'permanent' 列。")
        except aiosqlite.OperationalError as e:
            if "duplicate column name" not in str(e):
                raise e

        try:
            await db.execute(
                'INSERT OR IGNORE INTO settings (key, value, description) VALUES (?, ?, ?)',
                ('autoreply_enabled', '0', '是否启用自动回复功能 (1=是, 0=否)')
            )
            logging.info("数据库迁移：成功添加自动回复开关设置。")
        except Exception as e:
            logging.warning(f"添加自动回复设置时出错: {e}")

        try:
            await db.execute('INSERT OR IGNORE INTO settings (key, value, description) VALUES (?, ?, ?)', ('ai_provider', 'gemini', '当前使用的AI提供商 (gemini, openai)'))
            
            await db.execute('INSERT OR IGNORE INTO settings (key, value, description) VALUES (?, ?, ?)', ('gemini_model_filter', 'gemini-2.5-flash', 'Gemini 内容审查模型'))
            await db.execute('INSERT OR IGNORE INTO settings (key, value, description) VALUES (?, ?, ?)', ('gemini_model_verification', 'gemini-2.5-flash-lite', 'Gemini 验证码生成模型'))
            await db.execute('INSERT OR IGNORE INTO settings (key, value, description) VALUES (?, ?, ?)', ('gemini_model_autoreply', 'gemini-2.5-flash', 'Gemini 自动回复模型'))

            await db.execute('INSERT OR IGNORE INTO settings (key, value, description) VALUES (?, ?, ?)', ('openai_model_filter', 'gpt-4.1', 'OpenAI 内容审查模型'))
            await db.execute('INSERT OR IGNORE INTO settings (key, value, description) VALUES (?, ?, ?)', ('openai_model_verification', 'gpt-4.1-mini', 'OpenAI 验证码生成模型'))
            await db.execute('INSERT OR IGNORE INTO settings (key, value, description) VALUES (?, ?, ?)', ('openai_model_autoreply', 'gpt-4.1', 'OpenAI 自动回复模型'))

            await db.execute("DELETE FROM settings WHERE key IN ('openai_model', 'gemini_model')")

            logging.info("数据库迁移：成功添加细分AI设置。")
        except Exception as e:
            logging.warning(f"添加AI设置时出错: {e}")

db_manager = DatabaseManager()
