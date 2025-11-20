from telegram import Update
from telegram.error import BadRequest
from telegram.ext import ContextTypes
from database import models as db
from services.verification import create_verification, is_verification_pending, get_pending_verification_message
from services.thread_manager import get_or_create_thread
from services.gemini_service import gemini_service
from utils.media_converter import sticker_to_image
from services.rate_limiter import rate_limiter
from config import config

async def _resend_message(update: Update, context: ContextTypes.DEFAULT_TYPE, thread_id: int):
    message = update.message
    
    if message.text:
        await context.bot.send_message(
            chat_id=config.FORUM_GROUP_ID,
            text=message.text,
            entities=message.entities,
            message_thread_id=thread_id,
            disable_web_page_preview=True
        )
    elif message.photo:
        await context.bot.send_photo(
            chat_id=config.FORUM_GROUP_ID,
            photo=message.photo[-1].file_id,
            caption=message.caption,
            caption_entities=message.caption_entities,
            message_thread_id=thread_id
        )
    elif message.animation:
        await context.bot.send_animation(
            chat_id=config.FORUM_GROUP_ID,
            animation=message.animation.file_id,
            caption=message.caption,
            caption_entities=message.caption_entities,
            message_thread_id=thread_id
        )
    elif message.video:
        await context.bot.send_video(
            chat_id=config.FORUM_GROUP_ID,
            video=message.video.file_id,
            caption=message.caption,
            caption_entities=message.caption_entities,
            message_thread_id=thread_id
        )
    elif message.document:
        await context.bot.send_document(
            chat_id=config.FORUM_GROUP_ID,
            document=message.document.file_id,
            caption=message.caption,
            caption_entities=message.caption_entities,
            message_thread_id=thread_id
        )
    elif message.audio:
        await context.bot.send_audio(
            chat_id=config.FORUM_GROUP_ID,
            audio=message.audio.file_id,
            caption=message.caption,
            caption_entities=message.caption_entities,
            message_thread_id=thread_id
        )
    elif message.voice:
        await context.bot.send_voice(
            chat_id=config.FORUM_GROUP_ID,
            voice=message.voice.file_id,
            caption=message.caption,
            caption_entities=message.caption_entities,
            message_thread_id=thread_id
        )
    elif message.video_note:
        await context.bot.send_video_note(
            chat_id=config.FORUM_GROUP_ID,
            video_note=message.video_note.file_id,
            message_thread_id=thread_id
        )
    elif message.sticker:
        await context.bot.send_sticker(
            chat_id=config.FORUM_GROUP_ID,
            sticker=message.sticker.file_id,
            message_thread_id=thread_id
        )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    is_over_limit, was_warned = await rate_limiter.check_user_rate_limit(user.id)
    
    if is_over_limit:
        if was_warned:
            await db.add_to_blacklist(
                user.id,
                reason="忽略速率限制警告，多次超出限制",
                blocked_by=config.BOT_ID,
                permanent=True
            )
            await db.set_user_blacklist_strikes(user.id, 99)
            await update.message.reply_text(
                "您收到速率警告后仍然超出速率限制，已被永久封禁。\n\n"
                "如有疑问请联系管理员。"
            )
            return
        else:
            await rate_limiter.mark_user_warned(user.id)
            await update.message.reply_text(
                f"警告：您发送消息过于频繁，已超过速率限制。\n\n"
                f"当前速率限制规则：每分钟最多 {config.MAX_MESSAGES_PER_MINUTE} 条消息。\n\n"
                f"请稍后再试。如果继续超出限制，您将被永久封禁。"
            )
            return
    
    if 'pending_update' in context.user_data:
        if context.user_data['pending_update'].update_id == update.update_id:
            context.user_data.pop('pending_update')
    
    
    is_blocked, is_permanent = await db.is_blacklisted(user.id)
    if is_blocked:
        if is_permanent:
            await update.message.reply_text("你已被永久封禁，如有疑问请联系管理员。")
            return
        
        
        if not config.AUTO_UNBLOCK_ENABLED:
            await update.message.reply_text("自动解封功能已禁用。请联系管理员进行申诉。")
            return

        from services.blacklist import start_unblock_process
        message, keyboard = await start_unblock_process(user.id)
        if message and keyboard:
            await update.message.reply_text(message, reply_markup=keyboard, parse_mode='Markdown')
        elif message:
            await update.message.reply_text(message)
        return
    
    
    user_data = await db.get_user(user.id)
    
    if not user_data:
        await db.add_user(
            user_id=user.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name,
            language_code=user.language_code
        )
        welcome_message = (
            f"你好, {user.first_name}!\n\n"
            "欢迎使用双向聊天机器人。\n"
            "你可以直接在这里发送消息，管理员会尽快回复你。\n\n"
            "不过，在你发送第一条消息前，请先完成人机验证。"
        )
        await update.message.reply_text(welcome_message)
        user_data = await db.get_user(user.id)

    if not user_data.get('is_verified'):
        if not config.VERIFICATION_ENABLED:
            await db.update_user_verification(user.id, is_verified=True)
        else:
            has_pending, is_expired = is_verification_pending(user.id)
            
            if has_pending and not is_expired:
                verification_data = get_pending_verification_message(user.id)
                if verification_data:
                    question, keyboard = verification_data
                    context.user_data['pending_update'] = update
                    await update.message.reply_text(
                        "您还有未完成的人机验证，请先完成验证后再发送消息。\n\n"
                        f"请完成人机验证: \n\n{question}",
                        reply_markup=keyboard
                    )
                    return
            else:
                context.user_data['pending_update'] = update
                question, keyboard = await create_verification(user.id)
                await update.message.reply_text(question, reply_markup=keyboard)
                return
    
    
    message = update.message
    image_bytes = None

    if message.photo:
        photo_file = await message.photo[-1].get_file()
        image_bytes = await photo_file.download_as_bytearray()
    elif message.sticker and not message.sticker.is_animated and not message.sticker.is_video:
        sticker_file = await message.sticker.get_file()
        sticker_bytes = await sticker_file.download_as_bytearray()
        image_bytes = await sticker_to_image(sticker_bytes)

    if message.video or message.animation:
        pass
    else:
        analyzing_message = await context.bot.send_message(
            chat_id=message.chat_id,
            text="正在通过AI分析内容是否包含垃圾信息...",
            reply_to_message_id=message.message_id
        )

        analysis_result = await gemini_service.analyze_message(message, image_bytes)
        if analysis_result.get("is_spam"):
            await db.save_filtered_message(
                user_id=user.id,
                message_id=message.message_id,
                content=message.text or message.caption,
                reason=analysis_result.get("reason"),
                media_type=message.photo and "photo" or message.sticker and "sticker",
                media_file_id=message.photo and message.photo[-1].file_id or message.sticker and message.sticker.file_id,
            )
            reason = analysis_result.get("reason", "未提供原因")
            await analyzing_message.edit_text(f"您的消息已被系统拦截，因此未被转发\n\n原因：{reason}")
            return
        else:
            await analyzing_message.delete()

    thread_id, is_new = await get_or_create_thread(update, context)
    if not thread_id:
        await update.message.reply_text("无法创建或找到您的话题，请联系管理员。")
        return
    
    forwarded_message_id = None
    try:
        if not is_new:
            if message.text:
                sent_msg = await context.bot.send_message(
                    chat_id=config.FORUM_GROUP_ID,
                    text=message.text,
                    entities=message.entities,
                    message_thread_id=thread_id,
                    disable_web_page_preview=True
                )
                forwarded_message_id = sent_msg.message_id
            else:
                await _resend_message(update, context, thread_id)
                pass
    except BadRequest as e:
        if "Message thread not found" in e.message:
            await db.update_user_thread_id(user.id, None)
            await db.update_user_verification(user.id, False)
            context.user_data['pending_update'] = update
            question, keyboard = await create_verification(user.id)
            full_message = (
                "您的话题已被关闭，请重新进行验证以发送消息。\n\n"
                f"{question}"
            )
            await update.message.reply_text(
                text=full_message,
                reply_markup=keyboard
            )
            return
        else:
            print(f"发送消息时发生未知错误: {e}")
            await update.message.reply_text("发送消息时发生未知错误，请稍后再试。")
            return
    
    if message.text and await db.get_autoreply_enabled():
        knowledge_base_content = await db.get_all_knowledge_content()
        if knowledge_base_content:
            autoreply_text = await gemini_service.generate_autoreply(
                message.text,
                knowledge_base_content
            )
            
            if autoreply_text:
                try:
                    await update.message.reply_text(
                        autoreply_text,
                        parse_mode='Markdown'
                    )
                except Exception as e:
                    print(f"Markdown解析失败，使用纯文本: {e}")
                    await update.message.reply_text(autoreply_text)
                
                if forwarded_message_id:
                    admin_notification = (
                        f"自动回复内容:\n\n"
                        f"{autoreply_text}"
                    )
                    try:
                        await context.bot.send_message(
                            chat_id=config.FORUM_GROUP_ID,
                            text=admin_notification,
                            message_thread_id=thread_id,
                            reply_to_message_id=forwarded_message_id,
                            parse_mode='Markdown'
                        )
                    except Exception as e:
                        print(f"发送自动回复通知给管理员失败（Markdown），尝试纯文本: {e}")
                        try:
                            admin_notification_plain = (
                                f"自动回复内容:\n\n"
                                f"{autoreply_text}"
                            )
                            await context.bot.send_message(
                                chat_id=config.FORUM_GROUP_ID,
                                text=admin_notification_plain,
                                message_thread_id=thread_id,
                                reply_to_message_id=forwarded_message_id
                            )
                        except Exception as e2:
                            print(f"发送自动回复通知给管理员失败: {e2}")
    
    if not (message.text and await db.get_autoreply_enabled() and forwarded_message_id):
        try:
            if not is_new and not forwarded_message_id:
                await _resend_message(update, context, thread_id)
        except BadRequest as e:
            if "Message thread not found" in e.message:
                await db.update_user_thread_id(user.id, None)
                await db.update_user_verification(user.id, False)
                context.user_data['pending_update'] = update
                question, keyboard = await create_verification(user.id)
                full_message = (
                    "您的话题已被关闭，请重新进行验证以发送消息。\n\n"
                    f"{question}"
                )
                await update.message.reply_text(
                    text=full_message,
                    reply_markup=keyboard
                )
                return
            else:
                print(f"发送消息时发生未知错误: {e}")
                await update.message.reply_text("发送消息时发生未知错误，请稍后再试。")
