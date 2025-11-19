import time
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.helpers import escape_markdown
from database import models as db
from services.gemini_service import gemini_service
from config import config


pending_unblocks = {}

async def block_user(user_id: int, reason: str, admin_id: int, permanent: bool = False):
    await db.add_to_blacklist(user_id, reason, admin_id, permanent)
    if permanent:
        await db.set_user_blacklist_strikes(user_id, 99)
        return f"用户 {user_id} 已被管理员永久拉黑。\n原因: {reason}"
    return f"用户 {user_id} 已被管理员拉黑。\n原因: {reason}"

async def unblock_user(user_id: int):
    await db.remove_from_blacklist(user_id)
    
    await db.set_user_blacklist_strikes(user_id, 0)
    return f"用户 {user_id} 已被管理员解封。"

async def start_unblock_process(user_id: int):
    is_blocked, is_permanent = await db.is_blacklisted(user_id)
    
    if is_permanent:
        return "您已被管理员永久封禁，无法通过申诉解封。", None

    challenge = await gemini_service.generate_verification_challenge()
    question = challenge['question']
    correct_answer = challenge['correct_answer']
    options = challenge['options']
    
    pending_unblocks[user_id] = {
        'answer': correct_answer,
        'attempts': 0,
        'created_at': time.time()
    }
    
    keyboard = [
        [InlineKeyboardButton(option, callback_data=f"unblock_{option}") for option in options]
    ]
    
    return (
        "您已被暂时封禁。\n\n"
        f"如果您认为这是误操作，请回答以下问题以自动解封：\n\n{question}"
    ), InlineKeyboardMarkup(keyboard)

async def verify_unblock_answer(user_id: int, user_answer: str):
    if user_id not in pending_unblocks:
        return "解封会话已过期或不存在。", False

    session = pending_unblocks[user_id]
    
    del pending_unblocks[user_id]
    
    if time.time() - session['created_at'] > config.VERIFICATION_TIMEOUT:
        return "解封超时，请重新发送消息以获取新问题。", False

    if user_answer == session['answer']:
        await db.remove_from_blacklist(user_id)
        
        await db.set_user_blacklist_strikes(user_id, 0)
        return "解封成功！您现在可以正常发送消息了。", True
    else:
        
        await db.add_to_blacklist(user_id, reason="解封验证失败", blocked_by=config.BOT_ID, permanent=True)
        await db.set_user_blacklist_strikes(user_id, 99)
        return "答案错误，解封失败。您已被永久封禁。", False

def _safe_text_for_markdown(text: str) -> str:
    if not text:
        return text
    
    dangerous_chars = r'_*[]()`'
    return "".join(f"\\{char}" if char in dangerous_chars else char for char in text)

async def get_blacklist_keyboard(page: int = 1, per_page: int = 5):
    total_count = await db.get_blacklist_count()
    
    if total_count == 0:
        return "黑名单中没有用户。", None

    total_pages = (total_count + per_page - 1) // per_page

    if page < 1:
        page = 1
    elif page > total_pages:
        page = total_pages

    offset = (page - 1) * per_page

    blacklist_users = await db.get_blacklist_paginated(limit=per_page, offset=offset)
    
    if not blacklist_users:
        return "黑名单中没有用户。", None

    keyboard = []
    message = f"黑名单用户列表 (第 {page}/{total_pages} 页)\n\n"
    
    for idx, user in enumerate(blacklist_users, 1):
        user_id = user.get('user_id')
        first_name = user.get('first_name') or 'N/A'
        username = user.get('username')
        reason = user.get('reason') or '无'
        
        safe_first_name = _safe_text_for_markdown(first_name)
        safe_username = _safe_text_for_markdown(username) if username else None
        safe_reason = _safe_text_for_markdown(reason)
        
        user_info = f"{safe_first_name}"
        if safe_username:
            user_info += f" (@{safe_username})"
        
        message += f"{idx}. {user_info} (`{user_id}`)\n原因: {safe_reason}\n\n"
        
        keyboard.append([
            InlineKeyboardButton(f"解封 {first_name}", callback_data=f"admin_unblock_{user_id}")
        ])
    
    navigation_buttons = []
    if page > 1:
        navigation_buttons.append(InlineKeyboardButton("上一页", callback_data=f"blacklist_page_{page - 1}"))
    if page < total_pages:
        navigation_buttons.append(InlineKeyboardButton("下一页", callback_data=f"blacklist_page_{page + 1}"))
    
    if navigation_buttons:
        keyboard.append(navigation_buttons)

    return message, InlineKeyboardMarkup(keyboard)
