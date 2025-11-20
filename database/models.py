from datetime import datetime
from .db_manager import db_manager



async def get_user(user_id: int):
    async with db_manager.get_connection() as db:
        async with db.execute(
            'SELECT * FROM users WHERE user_id = ?',
            (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return dict(zip([col[0] for col in cursor.description], row))
            return None

async def add_user(user_id: int, username: str, first_name: str, last_name: str = None, language_code: str = None):
    async with db_manager.get_connection() as db:
        await db.execute('''
            INSERT OR REPLACE INTO users
            (user_id, username, first_name, last_name, language_code, last_active)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (user_id, username, first_name, last_name, language_code, datetime.now()))
        await db.commit()

async def update_user_verification(user_id: int, is_verified: bool):
    async with db_manager.get_connection() as db:
        await db.execute(
            'UPDATE users SET is_verified = ? WHERE user_id = ?',
            (1 if is_verified else 0, user_id)
        )
        await db.commit()

async def update_user_thread_id(user_id: int, thread_id: int):
    async with db_manager.get_connection() as db:
        await db.execute(
            'UPDATE users SET thread_id = ? WHERE user_id = ?',
            (thread_id, user_id)
        )
        await db.commit()

async def get_user_by_thread_id(thread_id: int):
    async with db_manager.get_connection() as db:
        async with db.execute(
            'SELECT * FROM users WHERE thread_id = ?',
            (thread_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return dict(zip([col[0] for col in cursor.description], row))
            return None



async def save_message(user_id: int, message_id: int, content: str, direction: str, media_type: str = None, media_file_id: str = None):
    async with db_manager.get_connection() as db:
        await db.execute('''
            INSERT INTO messages
            (user_id, message_id, content, direction, media_type, media_file_id)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (user_id, message_id, content, direction, media_type, media_file_id))
        await db.commit()

async def save_filtered_message(user_id: int, message_id: int, content: str, reason: str, media_type: str = None, media_file_id: str = None):
    async with db_manager.get_connection() as db:
        await db.execute('''
            INSERT INTO filtered_messages
            (user_id, message_id, content, reason, media_type, media_file_id)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (user_id, message_id, content, reason, media_type, media_file_id))
        await db.commit()

async def get_filtered_messages(limit: int = 20, offset: int = 0):
    async with db_manager.get_connection() as db:
        async with db.execute('''
            SELECT fm.*, u.first_name, u.username
            FROM filtered_messages fm
            JOIN users u ON fm.user_id = u.user_id
            ORDER BY fm.filtered_at DESC
            LIMIT ? OFFSET ?
        ''', (limit, offset)) as cursor:
            rows = await cursor.fetchall()
            if not rows:
                return []
            cols = [description[0] for description in cursor.description]
            return [dict(zip(cols, row)) for row in rows]

async def get_filtered_messages_count() -> int:
    async with db_manager.get_connection() as db:
        async with db.execute('SELECT COUNT(*) FROM filtered_messages') as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0



async def is_blacklisted(user_id: int):
    async with db_manager.get_connection() as db:
        async with db.execute(
            'SELECT permanent FROM blacklist WHERE user_id = ?',
            (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return True, bool(row[0])
            return False, False

async def add_to_blacklist(user_id: int, reason: str, blocked_by: int, permanent: bool = False):
    async with db_manager.get_connection() as db:
        await db.execute(
            'UPDATE users SET is_blacklisted = 1, blacklist_strikes = blacklist_strikes + 1 WHERE user_id = ?',
            (user_id,)
        )
        await db.execute('''
            INSERT OR REPLACE INTO blacklist (user_id, reason, blocked_by, permanent)
            VALUES (?, ?, ?, ?)
        ''', (user_id, reason, blocked_by, 1 if permanent else 0))
        await db.commit()

async def remove_from_blacklist(user_id: int):
    async with db_manager.get_connection() as db:
        await db.execute(
            'UPDATE users SET is_blacklisted = 0 WHERE user_id = ?',
            (user_id,)
        )
        await db.execute('DELETE FROM blacklist WHERE user_id = ?', (user_id,))
        await db.commit()

async def get_blacklist():
    async with db_manager.get_connection() as db:
        async with db.execute('''
            SELECT b.user_id, u.first_name, u.username, b.reason, b.blocked_at
            FROM blacklist b
            LEFT JOIN users u ON b.user_id = u.user_id
            ORDER BY b.blocked_at DESC
        ''') as cursor:
            rows = await cursor.fetchall()
            if not rows:
                return []
            
            
            cols = [description[0] for description in cursor.description]
            return [dict(zip(cols, row)) for row in rows]

async def get_blacklist_paginated(limit: int = 5, offset: int = 0):
    async with db_manager.get_connection() as db:
        async with db.execute('''
            SELECT b.user_id, u.first_name, u.username, b.reason, b.blocked_at
            FROM blacklist b
            LEFT JOIN users u ON b.user_id = u.user_id
            ORDER BY b.blocked_at DESC
            LIMIT ? OFFSET ?
        ''', (limit, offset)) as cursor:
            rows = await cursor.fetchall()
            if not rows:
                return []
            
            cols = [description[0] for description in cursor.description]
            return [dict(zip(cols, row)) for row in rows]

async def get_blacklist_count() -> int:
    async with db_manager.get_connection() as db:
        async with db.execute('SELECT COUNT(*) FROM blacklist') as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0

async def set_user_blacklist_strikes(user_id: int, strikes: int):
    async with db_manager.get_connection() as db:
        
        await db.execute(
            'INSERT OR IGNORE INTO users (user_id, first_name) VALUES (?, ?)',
            (user_id, f"User_{user_id}")
        )
        
        await db.execute(
            'UPDATE users SET blacklist_strikes = ? WHERE user_id = ?',
            (strikes, user_id)
        )
        await db.commit()



from config import config

async def is_admin(user_id: int) -> bool:
    return user_id in config.ADMIN_IDS

async def get_total_users_count() -> int:
    async with db_manager.get_connection() as db:
        async with db.execute('SELECT COUNT(*) FROM users') as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0

async def get_blocked_users_count() -> int:
    async with db_manager.get_connection() as db:
        async with db.execute('SELECT COUNT(*) FROM blacklist') as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0

async def get_user_spam_count(user_id: int) -> int:
    async with db_manager.get_connection() as db:
        async with db.execute('SELECT COUNT(*) FROM filtered_messages WHERE user_id = ?', (user_id,)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0

async def get_all_users_paginated(limit: int = 5, offset: int = 0):
    async with db_manager.get_connection() as db:
        async with db.execute('''
            SELECT 
                u.user_id,
                u.first_name,
                u.username,
                u.is_blacklisted,
                COALESCE(spam_count.count, 0) as spam_count
            FROM users u
            LEFT JOIN (
                SELECT user_id, COUNT(*) as count
                FROM filtered_messages
                GROUP BY user_id
            ) spam_count ON u.user_id = spam_count.user_id
            ORDER BY u.created_at DESC
            LIMIT ? OFFSET ?
        ''', (limit, offset)) as cursor:
            rows = await cursor.fetchall()
            if not rows:
                return []
            
            cols = [description[0] for description in cursor.description]
            return [dict(zip(cols, row)) for row in rows]

async def get_blacklist_user_details(user_id: int):
    async with db_manager.get_connection() as db:
        async with db.execute('''
            SELECT 
                b.user_id,
                u.first_name,
                u.username,
                u.last_name,
                u.language_code,
                u.is_blacklisted,
                u.blacklist_strikes,
                b.reason,
                b.blocked_by,
                b.blocked_at,
                b.permanent,
                COALESCE(spam_count.count, 0) as spam_count
            FROM blacklist b
            LEFT JOIN users u ON b.user_id = u.user_id
            LEFT JOIN (
                SELECT user_id, COUNT(*) as count
                FROM filtered_messages
                GROUP BY user_id
            ) spam_count ON b.user_id = spam_count.user_id
            WHERE b.user_id = ?
        ''', (user_id,)) as cursor:
            row = await cursor.fetchone()
            if row:
                cols = [description[0] for description in cursor.description]
                return dict(zip(cols, row))
            return None

async def add_knowledge_entry(title: str, content: str):
    async with db_manager.get_connection() as db:
        await db.execute('''
            INSERT INTO knowledge_base (title, content, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
        ''', (title, content))
        await db.commit()

async def get_all_knowledge_entries():
    async with db_manager.get_connection() as db:
        async with db.execute('''
            SELECT id, title, content, created_at, updated_at
            FROM knowledge_base
            ORDER BY updated_at DESC
        ''') as cursor:
            rows = await cursor.fetchall()
            if not rows:
                return []
            cols = [description[0] for description in cursor.description]
            return [dict(zip(cols, row)) for row in rows]

async def get_knowledge_entry(knowledge_id: int):
    async with db_manager.get_connection() as db:
        async with db.execute('''
            SELECT id, title, content, created_at, updated_at
            FROM knowledge_base
            WHERE id = ?
        ''', (knowledge_id,)) as cursor:
            row = await cursor.fetchone()
            if row:
                cols = [description[0] for description in cursor.description]
                return dict(zip(cols, row))
            return None

async def update_knowledge_entry(knowledge_id: int, title: str, content: str):
    async with db_manager.get_connection() as db:
        await db.execute('''
            UPDATE knowledge_base
            SET title = ?, content = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        ''', (title, content, knowledge_id))
        await db.commit()

async def delete_knowledge_entry(knowledge_id: int):
    async with db_manager.get_connection() as db:
        await db.execute('DELETE FROM knowledge_base WHERE id = ?', (knowledge_id,))
        await db.commit()

async def get_all_knowledge_content() -> str:
    entries = await get_all_knowledge_entries()
    if not entries:
        return ""
    
    knowledge_text = "知识库内容：\n\n"
    for entry in entries:
        knowledge_text += f"标题：{entry['title']}\n"
        knowledge_text += f"内容：{entry['content']}\n\n"
    
    return knowledge_text

async def get_autoreply_enabled() -> bool:
    async with db_manager.get_connection() as db:
        async with db.execute(
            'SELECT value FROM settings WHERE key = ?',
            ('autoreply_enabled',)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return row[0] == '1'
            return False

async def set_autoreply_enabled(enabled: bool):
    async with db_manager.get_connection() as db:
        await db.execute(
            'UPDATE settings SET value = ?, updated_at = CURRENT_TIMESTAMP WHERE key = ?',
            ('1' if enabled else '0', 'autoreply_enabled')
        )
        await db.commit()