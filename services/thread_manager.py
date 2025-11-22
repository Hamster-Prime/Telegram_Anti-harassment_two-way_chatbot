from telegram import Update
from telegram.ext import ContextTypes
from telegram.helpers import escape_markdown
from database import models as db
from config import config
from datetime import datetime
from utils.message_sender import send_message_by_type

async def get_or_create_thread(update: Update, context: ContextTypes.DEFAULT_TYPE) -> tuple[int, bool]:
    user = update.effective_user
    user_data = await db.get_user(user.id)
    
    if user_data and user_data.get('thread_id'):
        return user_data['thread_id'], False
    
    topic_name = f"{user.first_name} (ID: {user.id})"
    try:
        topic = await context.bot.create_forum_topic(
            chat_id=config.FORUM_GROUP_ID,
            name=topic_name
        )
        thread_id = topic.message_thread_id
        
        await db.update_user_thread_id(user.id, thread_id)
        
        await send_user_info_card(update, context, thread_id)
        
        return thread_id, True
    except Exception as e:
        print(f"创建话题失败: {e}")
        return None, False

async def send_user_info_card(update: Update, context: ContextTypes.DEFAULT_TYPE, thread_id: int):
    user = update.effective_user
    
    photos = await context.bot.get_user_profile_photos(user.id, limit=1)
    
    first_name = escape_markdown(user.first_name or '', version=2)
    last_name = escape_markdown(user.last_name or '', version=2)
    username = f"@{escape_markdown(user.username, version=2)}" if user.username else "无"

    info_text = (
        f"**用户信息**\n\n"
        f"**名称:** {first_name} {last_name}\n"
        f"**TG ID:** `{user.id}`\n"
        f"**用户名:** {username}\n"
        f"**首次联系:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    )
    
    if photos and photos.total_count > 0:
        await context.bot.send_photo(
            chat_id=config.FORUM_GROUP_ID,
            photo=photos.photos[0][0].file_id,
            caption=info_text,
            message_thread_id=thread_id,
            parse_mode='Markdown'
        )
    else:
        await context.bot.send_message(
            chat_id=config.FORUM_GROUP_ID,
            text=info_text,
            message_thread_id=thread_id,
            parse_mode='Markdown'
        )
    
    from handlers.user_handler import _resend_message
    await _resend_message(update, context, thread_id)
