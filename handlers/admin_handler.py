from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database import models as db

async def _send_reply_to_user(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int):
    message = update.message
    
    
    if message.text:
        await context.bot.send_message(
            chat_id=user_id,
            text=message.text,
            entities=message.entities,
            disable_web_page_preview=True
        )
    elif message.photo:
        await context.bot.send_photo(
            chat_id=user_id,
            photo=message.photo[-1].file_id,
            caption=message.caption,
            caption_entities=message.caption_entities
        )
    elif message.animation:
        await context.bot.send_animation(
            chat_id=user_id,
            animation=message.animation.file_id,
            caption=message.caption,
            caption_entities=message.caption_entities
        )
    elif message.video:
        await context.bot.send_video(
            chat_id=user_id,
            video=message.video.file_id,
            caption=message.caption,
            caption_entities=message.caption_entities
        )
    elif message.document:
        await context.bot.send_document(
            chat_id=user_id,
            document=message.document.file_id,
            caption=message.caption,
            caption_entities=message.caption_entities
        )
    elif message.audio:
        await context.bot.send_audio(
            chat_id=user_id,
            audio=message.audio.file_id,
            caption=message.caption,
            caption_entities=message.caption_entities
        )
    elif message.voice:
        await context.bot.send_voice(
            chat_id=user_id,
            voice=message.voice.file_id,
            caption=message.caption,
            caption_entities=message.caption_entities
        )
    elif message.video_note:
        await context.bot.send_video_note(
            chat_id=user_id,
            video_note=message.video_note.file_id
        )
    elif message.sticker:
        await context.bot.send_sticker(
            chat_id=user_id,
            sticker=message.sticker.file_id
        )

async def handle_admin_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.is_topic_message:
        return
    
    thread_id = update.message.message_thread_id
    
    
    user = await db.get_user_by_thread_id(thread_id)
    if not user:
        return
    
    user_id = user['user_id']
    
    await _send_reply_to_user(update, context, user_id)

async def _format_filtered_messages(messages, page: int, total_pages: int):
    response = f"被过滤的消息 (第 {page}/{total_pages} 页):\n\n"
    
    for idx, msg in enumerate(messages, 1):
        first_name = msg.get('first_name') or 'N/A'
        username = msg.get('username') or 'N/A'
        reason = msg.get('reason') or 'N/A'
        content = msg.get('content') or 'N/A'
        filtered_at = msg.get('filtered_at') or 'N/A'

        if content and len(content) > 100:
            content = content[:100] + "..."
        
        response += (
            f"【{idx}】\n"
            f"用户: {first_name} (@{username})\n"
            f"原因: {reason}\n"
            f"内容: {content}\n"
            f"时间: {filtered_at}\n\n"
        )
    
    return response

async def _get_filtered_messages_keyboard(page: int, total_pages: int):
    keyboard = []
    
    if total_pages <= 1:
        return None
    
    buttons = []
    
    if page > 1:
        buttons.append(InlineKeyboardButton("上一页", callback_data=f"filtered_page_{page - 1}"))
    
    if page < total_pages:
        buttons.append(InlineKeyboardButton("下一页", callback_data=f"filtered_page_{page + 1}"))
    
    if buttons:
        keyboard.append(buttons)
    
    return InlineKeyboardMarkup(keyboard) if keyboard else None

async def view_filtered(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await db.is_admin(update.effective_user.id):
        await update.message.reply_text("您没有权限执行此操作。")
        return

    MESSAGES_PER_PAGE = 5
    page = 1

    total_count = await db.get_filtered_messages_count()
    
    if total_count == 0:
        await update.message.reply_text("没有找到被过滤的消息。")
        return
    
    total_pages = (total_count + MESSAGES_PER_PAGE - 1) // MESSAGES_PER_PAGE

    offset = (page - 1) * MESSAGES_PER_PAGE

    messages = await db.get_filtered_messages(MESSAGES_PER_PAGE, offset)
    
    if not messages:
        await update.message.reply_text("没有找到被过滤的消息。")
        return

    response = await _format_filtered_messages(messages, page, total_pages)

    keyboard = await _get_filtered_messages_keyboard(page, total_pages)

    if keyboard:
        await update.message.reply_text(response, reply_markup=keyboard)
    else:
        await update.message.reply_text(response)