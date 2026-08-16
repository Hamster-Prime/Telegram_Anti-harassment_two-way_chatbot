from telegram import ReplyParameters, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database import models as db
from services.media_group_buffer import enqueue_message, replace_buffered_update
from services.message_relay import relay_media_group, relay_message, sync_edited_message

async def _send_reply_to_user(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int):
    return await relay_message(
        bot=context.bot,
        message=update.effective_message,
        destination_chat_id=user_id,
        user_id=user_id,
        source_side="admin",
    )

async def handle_admin_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.is_topic_message:
        return

    if not update.effective_user or not await db.is_admin(update.effective_user.id):
        return

    thread_id = update.message.message_thread_id
    user = await db.get_user_by_thread_id(thread_id)
    if not user:
        return

    accepted = await enqueue_message(
        update,
        context,
        scope="admin",
        callback=_handle_admin_messages,
        conversation_id=user["user_id"],
    )
    if not accepted:
        await update.message.reply_text(
            "当前消息队列繁忙，这条消息尚未传递，请稍后重新发送。"
        )


async def _handle_admin_messages(updates, context: ContextTypes.DEFAULT_TYPE):
    first_message = updates[0].effective_message
    user = await db.get_user_by_thread_id(first_message.message_thread_id)
    if not user:
        return

    if len(updates) == 1:
        await _send_reply_to_user(updates[0], context, user["user_id"])
        return

    await relay_media_group(
        bot=context.bot,
        messages=[update.effective_message for update in updates],
        destination_chat_id=user["user_id"],
        user_id=user["user_id"],
        source_side="admin",
    )


async def handle_admin_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.edited_message
    if not message or not message.is_topic_message:
        return

    if not update.effective_user or not await db.is_admin(update.effective_user.id):
        return

    user = await db.get_user_by_thread_id(message.message_thread_id)
    if not user:
        return

    if replace_buffered_update(
        update,
        context,
        scope="admin",
        conversation_id=user["user_id"],
    ):
        return

    accepted = await enqueue_message(
        update,
        context,
        scope="admin-edit",
        callback=_handle_admin_edits,
        conversation_id=user["user_id"],
    )
    if not accepted:
        await context.bot.send_message(
            chat_id=message.chat_id,
            message_thread_id=message.message_thread_id,
            text="当前消息队列繁忙，这次编辑尚未同步，请稍后再次编辑。",
            reply_parameters=ReplyParameters(
                message_id=message.message_id,
                allow_sending_without_reply=True,
            ),
        )


async def _handle_admin_edits(updates, context: ContextTypes.DEFAULT_TYPE):
    message = updates[-1].edited_message
    if not message:
        return

    user = await db.get_user_by_thread_id(message.message_thread_id)
    if not user:
        return

    synced = await sync_edited_message(
        bot=context.bot,
        message=message,
        user_id=user["user_id"],
        source_side="admin",
    )
    if not synced:
        await context.bot.send_message(
            chat_id=message.chat_id,
            message_thread_id=message.message_thread_id,
            text="这次编辑未能同步到用户侧，请稍后再次编辑或重新发送。",
            reply_parameters=ReplyParameters(
                message_id=message.message_id,
                allow_sending_without_reply=True,
            ),
        )

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

async def _get_filtered_messages_keyboard(page: int, total_pages: int, callback_prefix: str = "filtered_page_"):
    keyboard = []
    
    if total_pages <= 1:
        return None
    
    buttons = []
    
    if page > 1:
        buttons.append(InlineKeyboardButton("上一页", callback_data=f"{callback_prefix}{page - 1}"))
    
    if page < total_pages:
        buttons.append(InlineKeyboardButton("下一页", callback_data=f"{callback_prefix}{page + 1}"))
    
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
