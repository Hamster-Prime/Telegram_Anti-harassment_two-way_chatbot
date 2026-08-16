import logging

from telegram import ReplyParameters, Update
from telegram.error import BadRequest
from telegram.ext import ContextTypes
from database import models as db
from services.verification import create_verification, is_verification_pending, get_pending_verification_message
from services.thread_manager import get_or_create_thread
from services.gemini_service import gemini_service
from services.media_group_buffer import (
    enqueue_message,
    has_active_queue,
    replace_buffered_update,
)
from services.message_relay import relay_media_group, relay_message, sync_edited_message
from utils.media_converter import sticker_to_image
from services.rate_limiter import rate_limiter
from config import config


logger = logging.getLogger(__name__)


async def handle_invalid_thread(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    pending_updates=None,
):
    await db.reset_user_relay_state(user_id)
    context.user_data['pending_updates'] = [pending_updates or [update]]
    question, keyboard = await create_verification(user_id)
    full_message = (
        "您的话题已被关闭，请重新进行验证以发送消息。\n\n"
        f"{question}"
    )
    await update.effective_message.reply_text(
        text=full_message,
        reply_markup=keyboard
    )

async def _resend_message(update: Update, context: ContextTypes.DEFAULT_TYPE, thread_id: int):
    return await relay_message(
        bot=context.bot,
        message=update.effective_message,
        destination_chat_id=config.FORUM_GROUP_ID,
        destination_thread_id=thread_id,
        user_id=update.effective_user.id,
        source_side="user",
    )


async def _message_passes_moderation(
    message,
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    rejection_action: str = "转发",
) -> bool:
    if await db.is_exempted(user_id):
        return True

    image_bytes = None
    if message.photo:
        photo_file = await message.photo[-1].get_file()
        image_bytes = await photo_file.download_as_bytearray()
    elif message.sticker and not message.sticker.is_animated and not message.sticker.is_video:
        sticker_file = await message.sticker.get_file()
        sticker_bytes = await sticker_file.download_as_bytearray()
        image_bytes = await sticker_to_image(sticker_bytes)

    analyzing_message = await context.bot.send_message(
        chat_id=message.chat_id,
        text="正在通过AI分析内容是否包含垃圾信息...",
        reply_to_message_id=message.message_id,
    )
    analysis_result = await gemini_service.analyze_message(message, image_bytes)
    if analysis_result.get("is_spam"):
        await db.save_filtered_message(
            user_id=user_id,
            message_id=message.message_id,
            content=message.text or message.caption,
            reason=analysis_result.get("reason"),
            media_type=message.photo and "photo" or message.sticker and "sticker",
            media_file_id=(
                message.photo and message.photo[-1].file_id
                or message.sticker and message.sticker.file_id
            ),
        )
        reason = analysis_result.get("reason", "未提供原因")
        await analyzing_message.edit_text(
            f"您的消息已被系统拦截，因此未{rejection_action}\n\n原因：{reason}"
        )
        return False

    try:
        await analyzing_message.delete()
    except Exception:
        logger.exception("清理内容审查状态消息失败，继续转发原消息")
    return True

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_user:
        return
    accepted = await enqueue_message(
        update,
        context,
        scope="user",
        callback=_handle_new_messages,
        conversation_id=update.effective_user.id,
    )
    if not accepted:
        await update.message.reply_text(
            "当前消息队列繁忙，这条消息尚未传递，请稍后重新发送。"
        )


async def _handle_new_messages(updates, context: ContextTypes.DEFAULT_TYPE):
    updates = sorted(updates, key=lambda item: item.effective_message.message_id)
    update = updates[0]
    message = update.effective_message
    user = update.effective_user

    if len(updates) == 1:
        from network_test.handlers import handle_message as network_handle_message
        network_update = update
        if getattr(update, "message", None) is None and isinstance(update, Update):
            network_update = Update(
                update_id=update.update_id,
                message=update.effective_message,
            )
        handled = await network_handle_message(network_update, context)
        if handled:
            return

    is_over_limit, was_warned = await rate_limiter.check_user_rate_limit(user.id)
    if is_over_limit:
        if was_warned:
            await db.add_to_blacklist(
                user.id,
                reason="忽略速率限制警告，多次超出限制",
                blocked_by=config.BOT_ID,
                permanent=True,
            )
            await db.set_user_blacklist_strikes(user.id, 99)
            await message.reply_text(
                "您收到速率警告后仍然超出速率限制，已被永久封禁。\n\n"
                "如有疑问请联系管理员。"
            )
        else:
            await rate_limiter.mark_user_warned(user.id)
            await message.reply_text(
                "警告：您发送消息过于频繁，已超过速率限制。\n\n"
                f"当前速率限制规则：每分钟最多 {config.MAX_MESSAGES_PER_MINUTE} 条消息。\n\n"
                "请稍后再试。如果继续超出限制，您将被永久封禁。"
            )
        return

    is_blocked, is_permanent = await db.is_blacklisted(user.id)
    if is_blocked:
        if is_permanent:
            await message.reply_text("你已被永久封禁，如有疑问请联系管理员。")
            return
        if not config.AUTO_UNBLOCK_ENABLED:
            await message.reply_text("自动解封功能已禁用。请联系管理员进行申诉。")
            return

        from services.blacklist import start_unblock_process
        response, keyboard = await start_unblock_process(user.id)
        if response and keyboard:
            await message.reply_text(response, reply_markup=keyboard, parse_mode="Markdown")
        elif response:
            await message.reply_text(response)
        return

    user_data = await db.get_user(user.id)
    if not user_data:
        await db.add_user(
            user_id=user.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name,
            language_code=user.language_code,
        )
        await message.reply_text(
            f"你好, {user.first_name}!\n\n"
            "欢迎使用双向聊天机器人。\n"
            "你可以直接在这里发送消息，管理员会尽快回复你。\n\n"
            "不过，在你发送第一条消息前，请先完成人机验证。"
        )
        user_data = await db.get_user(user.id)
    else:
        await db.update_user_profile(
            user_id=user.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name,
            language_code=user.language_code,
        )

    if not user_data.get("is_verified"):
        if not config.VERIFICATION_ENABLED:
            await db.update_user_verification(user.id, is_verified=True)
        else:
            _append_pending_batch(context, updates)
            has_pending, is_expired = is_verification_pending(user.id)
            if has_pending and not is_expired:
                verification_data = get_pending_verification_message(user.id)
                if verification_data:
                    question, keyboard = verification_data
                    await message.reply_text(
                        "您还有未完成的人机验证，请先完成验证后再发送消息。\n\n"
                        f"请完成人机验证: \n\n{question}",
                        reply_markup=keyboard,
                    )
                    return

            question, keyboard = await create_verification(user.id)
            await message.reply_text(question, reply_markup=keyboard)
            return

    if _pending_batches(context):
        _append_pending_batch(context, updates)
        await _forward_pending_batches(context, user.id)
        return

    try:
        outcome = await _forward_verified_messages(updates, context, user.id)
    except Exception:
        if not _pending_batches(context):
            context.user_data["pending_updates"] = [list(updates)]
        raise
    if outcome is False and not _pending_batches(context):
        context.user_data["pending_updates"] = [list(updates)]


def _pending_batches(context: ContextTypes.DEFAULT_TYPE) -> list[list[Update]]:
    pending = context.user_data.get("pending_updates")
    legacy_pending = context.user_data.pop("pending_update", None)
    if not pending:
        batches = [[legacy_pending]] if legacy_pending else []
        if batches:
            context.user_data["pending_updates"] = batches
        return batches
    if isinstance(pending[0], (list, tuple)):
        batches = pending
    else:
        batches = [list(pending)]

    if legacy_pending:
        batches.insert(0, [legacy_pending])
    context.user_data["pending_updates"] = batches
    return batches


def _append_pending_batch(context: ContextTypes.DEFAULT_TYPE, updates) -> None:
    batch = sorted(
        updates,
        key=lambda item: item.effective_message.message_id,
    )
    batches = _pending_batches(context)
    batches.append(batch)
    context.user_data["pending_updates"] = batches


def _is_missing_thread_error(error: BadRequest) -> bool:
    error_text = error.message.lower()
    return any(
        marker in error_text
        for marker in (
            "thread not found",
            "topic not found",
        )
    )


def _is_closed_thread_error(error: BadRequest) -> bool:
    error_text = error.message.lower()
    return any(
        marker in error_text
        for marker in (
            "thread is closed",
            "thread has been closed",
            "topic closed",
            "topic is closed",
            "topic was closed",
            "topic_closed",
        )
    )


async def _forward_verified_messages(
    updates,
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
):
    updates = sorted(updates, key=lambda item: item.effective_message.message_id)
    update = updates[0]
    messages = [item.effective_message for item in updates]

    for message in messages:
        if not await _message_passes_moderation(message, context, user_id):
            return True

    is_media_group = len(messages) > 1 and bool(messages[0].media_group_id)
    thread_id, _ = await get_or_create_thread(update, context)
    if not thread_id:
        await messages[0].reply_text("无法创建或找到您的话题，请联系管理员。")
        return False

    forwarded_message_id = None
    for attempt in range(2):
        try:
            if is_media_group:
                copied_messages = await relay_media_group(
                    bot=context.bot,
                    messages=messages,
                    destination_chat_id=config.FORUM_GROUP_ID,
                    destination_thread_id=thread_id,
                    user_id=user_id,
                    source_side="user",
                )
                forwarded_message_id = copied_messages[0].message_id
            else:
                copied = await _resend_message(update, context, thread_id)
                forwarded_message_id = copied.message_id
            break
        except BadRequest as error:
            if attempt == 0 and _is_closed_thread_error(error):
                try:
                    await context.bot.reopen_forum_topic(
                        chat_id=config.FORUM_GROUP_ID,
                        message_thread_id=thread_id,
                    )
                except BadRequest as reopen_error:
                    if "not modified" not in reopen_error.message.lower():
                        logger.warning("重新打开话题 %s 失败: %s", thread_id, reopen_error)
                        await messages[0].reply_text(
                            "您的话题暂时无法重新打开，请稍后再试。"
                        )
                        return False
                except Exception:
                    logger.exception("重新打开话题 %s 时发生错误", thread_id)
                    await messages[0].reply_text(
                        "您的话题暂时无法重新打开，请稍后再试。"
                    )
                    return False
                continue
            if _is_missing_thread_error(error):
                await handle_invalid_thread(
                    update,
                    context,
                    user_id,
                    pending_updates=updates,
                )
            else:
                logger.warning("发送消息时发生 Telegram 错误: %s", error)
                await messages[0].reply_text("发送消息时发生未知错误，请稍后再试。")
            return False
        except Exception:
            logger.exception("发送消息或保存映射失败")
            await messages[0].reply_text("发送消息时发生未知错误，请稍后再试。")
            return False

    if forwarded_message_id is None:
        return False

    try:
        await _send_autoreply_if_enabled(
            update=update,
            context=context,
            user_id=user_id,
            thread_id=thread_id,
            forwarded_message_id=forwarded_message_id,
        )
    except Exception:
        logger.exception("自动回复发送失败，原始消息已成功转发")
    return True


async def _forward_pending_batches(
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
) -> bool:
    batches = [list(batch) for batch in _pending_batches(context)]
    if not batches:
        return False

    context.user_data.pop("pending_update", None)
    context.user_data["pending_updates"] = batches
    while batches:
        active_batches = batches
        outcome = await _forward_verified_messages(
            batches[0],
            context,
            user_id,
        )
        if outcome is False:
            if context.user_data.get("pending_updates") is not active_batches:
                replacement = [
                    list(batch) for batch in _pending_batches(context)
                ]
                context.user_data["pending_updates"] = replacement + batches[1:]
            return False
        batches = batches[1:]
        if batches:
            context.user_data["pending_updates"] = batches
        else:
            context.user_data.pop("pending_updates", None)
    return True


async def _delete_message_safely(bot, chat_id: int, message_id: int):
    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
    except Exception as error:
        logger.warning("清理未配对消息 %s:%s 失败: %s", chat_id, message_id, error)


async def _send_autoreply_if_enabled(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    thread_id: int,
    forwarded_message_id: int,
):
    message = update.effective_message
    if not message.text or not await db.get_autoreply_enabled():
        return

    knowledge_base_content = await db.get_all_knowledge_content()
    if not knowledge_base_content:
        return
    autoreply_text = await gemini_service.generate_autoreply(
        message.text,
        knowledge_base_content,
    )
    if not autoreply_text:
        return

    reply_parameters = ReplyParameters(
        message_id=message.message_id,
        allow_sending_without_reply=True,
    )
    try:
        user_autoreply = await message.reply_text(
            autoreply_text,
            parse_mode="Markdown",
            reply_parameters=reply_parameters,
        )
    except BadRequest as error:
        error_text = error.message.lower()
        if not any(
            marker in error_text
            for marker in (
                "can't parse entities",
                "can't find end",
                "unsupported start tag",
                "unsupported end tag",
            )
        ):
            raise
        logger.warning("自动回复 Markdown 解析失败，使用纯文本: %s", error)
        user_autoreply = await message.reply_text(
            autoreply_text,
            reply_parameters=reply_parameters,
        )

    try:
        admin_autoreply = await context.bot.send_message(
            chat_id=config.FORUM_GROUP_ID,
            text=user_autoreply.text,
            entities=user_autoreply.entities,
            message_thread_id=thread_id,
            reply_parameters=ReplyParameters(
                message_id=forwarded_message_id,
                allow_sending_without_reply=True,
            ),
        )
    except Exception as error:
        logger.warning("管理员侧自动回复发送失败，撤销用户侧消息: %s", error)
        await _delete_message_safely(
            context.bot,
            message.chat_id,
            user_autoreply.message_id,
        )
        return

    try:
        await db.save_message_mapping(
            user_id=user_id,
            user_chat_id=message.chat_id,
            user_message_id=user_autoreply.message_id,
            admin_chat_id=config.FORUM_GROUP_ID,
            admin_message_id=admin_autoreply.message_id,
            thread_id=thread_id,
            origin_side="admin",
        )
    except Exception:
        logger.exception("自动回复映射保存失败，撤销两侧消息")
        await _delete_message_safely(
            context.bot,
            message.chat_id,
            user_autoreply.message_id,
        )
        await _delete_message_safely(
            context.bot,
            config.FORUM_GROUP_ID,
            admin_autoreply.message_id,
        )


def _replace_pending_update(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    message = update.edited_message
    if not message:
        return False

    for batch in _pending_batches(context):
        for index, pending_update in enumerate(batch):
            pending_message = pending_update.effective_message
            if (
                pending_message
                and pending_message.chat_id == message.chat_id
                and pending_message.message_id == message.message_id
            ):
                batch[index] = update
                batch.sort(
                    key=lambda item: item.effective_message.message_id
                )
                return True

    legacy_pending = context.user_data.get("pending_update")
    legacy_message = legacy_pending and legacy_pending.effective_message
    if (
        legacy_message
        and legacy_message.chat_id == message.chat_id
        and legacy_message.message_id == message.message_id
    ):
        context.user_data["pending_update"] = update
        return True

    return False


async def handle_edited_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.edited_message
    user = update.effective_user
    if not message or not user:
        return

    if (
        not has_active_queue(context, user.id)
        and _replace_pending_update(update, context)
    ):
        return

    if replace_buffered_update(
        update,
        context,
        scope="user",
        conversation_id=user.id,
    ):
        return

    accepted = await enqueue_message(
        update,
        context,
        scope="user-edit",
        callback=_handle_user_edit_batch,
        conversation_id=user.id,
    )
    if not accepted:
        await message.reply_text(
            "当前消息队列繁忙，这次编辑尚未同步，请稍后再次编辑。",
            reply_parameters=ReplyParameters(
                message_id=message.message_id,
                allow_sending_without_reply=True,
            ),
        )


async def _handle_user_edit_batch(updates, context: ContextTypes.DEFAULT_TYPE):
    await _handle_edited_message_now(updates[-1], context)


async def _handle_edited_message_now(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    message = update.edited_message
    user = update.effective_user
    if not message or not user:
        return

    if _replace_pending_update(update, context):
        return

    mapping = await db.get_message_mapping_by_user_endpoint(
        message.chat_id,
        message.message_id,
    )
    if not mapping or mapping["user_id"] != user.id:
        return

    is_blocked, _ = await db.is_blacklisted(user.id)
    if is_blocked:
        return

    if not await _message_passes_moderation(
        message,
        context,
        user.id,
        rejection_action="同步编辑",
    ):
        try:
            await context.bot.send_message(
                chat_id=mapping["admin_chat_id"],
                message_thread_id=mapping["thread_id"],
                text="用户对这条消息的编辑未通过内容审查，当前仍保留上一版本。",
                reply_parameters=ReplyParameters(
                    message_id=mapping["admin_message_id"],
                    allow_sending_without_reply=True,
                ),
            )
        except Exception:
            logger.exception("发送用户编辑拦截通知失败")
        return

    synced = await sync_edited_message(
        bot=context.bot,
        message=message,
        user_id=user.id,
        source_side="user",
    )
    if not synced:
        await message.reply_text(
            "这次编辑未能同步到管理员侧，请稍后再次编辑或重新发送。",
            reply_parameters=ReplyParameters(
                message_id=message.message_id,
                allow_sending_without_reply=True,
            ),
        )
