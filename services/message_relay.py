import asyncio
import logging
from typing import Literal, Optional, Sequence

from telegram import (
    InputMediaAnimation,
    InputMediaAudio,
    InputMediaDocument,
    InputMediaPhoto,
    InputMediaVideo,
    Message,
    MessageId,
    ReplyParameters,
)
from telegram.error import BadRequest, NetworkError, RetryAfter

from database import models as db


logger = logging.getLogger(__name__)
_EDIT_RETRY_DELAYS = (0.25, 0.75)
_MAX_RETRY_AFTER_SECONDS = 5.0

RelaySide = Literal["user", "admin"]


async def _get_mapping(message: Message, user_id: int, source_side: RelaySide):
    if source_side == "user":
        return await db.get_message_mapping_by_user_endpoint(
            message.chat_id,
            message.message_id,
        )
    return await db.get_message_mapping_by_admin_endpoint(
        message.chat_id,
        message.message_id,
    )


async def _mappings_are_persisted(mappings: Sequence[dict]) -> bool:
    try:
        for expected in mappings:
            by_user = await db.get_message_mapping_by_user_endpoint(
                expected["user_chat_id"],
                expected["user_message_id"],
            )
            if not by_user:
                return False
            by_admin = await db.get_message_mapping_by_admin_endpoint(
                expected["admin_chat_id"],
                expected["admin_message_id"],
            )
            if not (
                by_user == by_admin
                and all(by_user.get(key) == value for key, value in expected.items())
            ):
                return False
        return True
    except Exception as error:
        logger.warning("无法确认消息映射是否已经保存: %s", error)
        return False


def _counterpart_id(mapping: dict, source_side: RelaySide) -> int:
    if source_side == "user":
        return mapping["admin_message_id"]
    return mapping["user_message_id"]


async def _build_reply_parameters(
    message: Message,
    user_id: int,
    source_side: RelaySide,
) -> Optional[ReplyParameters]:
    replied_message = message.reply_to_message
    if not replied_message:
        external_reply = message.external_reply
        if not (
            external_reply
            and external_reply.chat
            and external_reply.message_id
        ):
            return None

        quote = message.quote
        return ReplyParameters(
            message_id=external_reply.message_id,
            chat_id=external_reply.chat.id,
            quote=quote.text if quote else None,
            quote_entities=quote.entities if quote else None,
            quote_position=quote.position if quote else None,
        )

    mapping = await _get_mapping(replied_message, user_id, source_side)
    if not mapping or mapping["user_id"] != user_id:
        return None

    quote = message.quote
    return ReplyParameters(
        message_id=_counterpart_id(mapping, source_side),
        allow_sending_without_reply=True,
        quote=quote.text if quote else None,
        quote_entities=quote.entities if quote else None,
        quote_position=quote.position if quote else None,
    )


def _without_quote(reply_parameters: ReplyParameters) -> ReplyParameters:
    kwargs = {
        "message_id": reply_parameters.message_id,
        "chat_id": reply_parameters.chat_id,
    }
    if reply_parameters.chat_id is None:
        kwargs["allow_sending_without_reply"] = True
    return ReplyParameters(**kwargs)


async def _copy_with_reply_fallback(
    bot,
    message: Message,
    destination_chat_id: int,
    destination_thread_id: Optional[int],
    reply_parameters: Optional[ReplyParameters],
) -> MessageId:
    base_kwargs = {
        "chat_id": destination_chat_id,
        "from_chat_id": message.chat_id,
        "message_id": message.message_id,
        "message_thread_id": destination_thread_id,
        "show_caption_above_media": message.show_caption_above_media,
    }

    attempts = []
    if reply_parameters:
        attempts.append(reply_parameters)
        if reply_parameters.quote is not None:
            attempts.append(_without_quote(reply_parameters))
    attempts.append(None)

    last_error = None
    for parameters in attempts:
        try:
            return await bot.copy_message(
                **base_kwargs,
                reply_parameters=parameters,
            )
        except BadRequest as error:
            last_error = error
            if parameters is None:
                raise
            logger.warning(
                "复制消息时无法保留回复或引用，正在降级重试: %s",
                error,
            )

    raise last_error


async def relay_message(
    bot,
    message: Message,
    destination_chat_id: int,
    user_id: int,
    source_side: RelaySide,
    destination_thread_id: Optional[int] = None,
) -> MessageId:
    existing = await _get_mapping(message, user_id, source_side)
    if existing:
        if existing["user_id"] != user_id:
            raise ValueError("消息端点已属于其他用户")
        return MessageId(_counterpart_id(existing, source_side))

    reply_parameters = await _build_reply_parameters(message, user_id, source_side)
    copied = await _copy_with_reply_fallback(
        bot=bot,
        message=message,
        destination_chat_id=destination_chat_id,
        destination_thread_id=destination_thread_id,
        reply_parameters=reply_parameters,
    )

    mapping = _mapping_for_copy(
        message=message,
        copied_message_id=copied.message_id,
        destination_chat_id=destination_chat_id,
        destination_thread_id=destination_thread_id,
        user_id=user_id,
        source_side=source_side,
    )

    try:
        await db.save_message_mapping(**mapping)
    except Exception:
        if await _mappings_are_persisted([mapping]):
            logger.warning("消息映射保存返回错误，但读回确认已经提交")
            return copied
        try:
            await bot.delete_message(destination_chat_id, copied.message_id)
        except Exception as cleanup_error:
            logger.error(
                "消息映射保存失败后无法删除目标副本 %s:%s: %s",
                destination_chat_id,
                copied.message_id,
                cleanup_error,
            )
        raise
    return copied


def _mapping_for_copy(
    message: Message,
    copied_message_id: int,
    destination_chat_id: int,
    destination_thread_id: Optional[int],
    user_id: int,
    source_side: RelaySide,
) -> dict:
    if source_side == "user":
        return {
            "user_id": user_id,
            "user_chat_id": message.chat_id,
            "user_message_id": message.message_id,
            "admin_chat_id": destination_chat_id,
            "admin_message_id": copied_message_id,
            "thread_id": destination_thread_id,
            "origin_side": "user",
        }
    return {
        "user_id": user_id,
        "user_chat_id": destination_chat_id,
        "user_message_id": copied_message_id,
        "admin_chat_id": message.chat_id,
        "admin_message_id": message.message_id,
        "thread_id": message.message_thread_id,
        "origin_side": "admin",
    }


def _editable_media(message: Message):
    common = {
        "caption": message.caption,
        "caption_entities": message.caption_entities,
    }

    if message.photo:
        return InputMediaPhoto(
            media=message.photo[-1].file_id,
            has_spoiler=message.has_media_spoiler,
            show_caption_above_media=message.show_caption_above_media,
            **common,
        )
    if message.video:
        cover = message.video.cover
        return InputMediaVideo(
            media=message.video.file_id,
            width=message.video.width,
            height=message.video.height,
            duration=message.video.duration,
            cover=cover[-1].file_id if cover else None,
            start_timestamp=message.video.start_timestamp,
            has_spoiler=message.has_media_spoiler,
            show_caption_above_media=message.show_caption_above_media,
            **common,
        )
    if message.animation:
        return InputMediaAnimation(
            media=message.animation.file_id,
            width=message.animation.width,
            height=message.animation.height,
            duration=message.animation.duration,
            has_spoiler=message.has_media_spoiler,
            show_caption_above_media=message.show_caption_above_media,
            **common,
        )
    if message.audio:
        return InputMediaAudio(
            media=message.audio.file_id,
            duration=message.audio.duration,
            performer=message.audio.performer,
            title=message.audio.title,
            **common,
        )
    if message.document:
        return InputMediaDocument(
            media=message.document.file_id,
            **common,
        )
    return None


async def _send_media_group_with_reply_fallback(
    bot,
    media: Sequence,
    destination_chat_id: int,
    destination_thread_id: Optional[int],
    reply_parameters: ReplyParameters,
):
    attempts = [reply_parameters]
    if reply_parameters.quote is not None:
        attempts.append(_without_quote(reply_parameters))
    attempts.append(None)

    for parameters in attempts:
        try:
            return await bot.send_media_group(
                chat_id=destination_chat_id,
                media=media,
                message_thread_id=destination_thread_id,
                reply_parameters=parameters,
            )
        except BadRequest:
            if parameters is None:
                raise
            logger.warning("发送相册时无法保留回复或引用，正在降级重试")


async def relay_media_group(
    bot,
    messages: Sequence[Message],
    destination_chat_id: int,
    user_id: int,
    source_side: RelaySide,
    destination_thread_id: Optional[int] = None,
) -> tuple[MessageId, ...]:
    ordered_messages = sorted(messages, key=lambda item: item.message_id)
    if not ordered_messages:
        raise ValueError("相册消息不能为空")
    if len(ordered_messages) < 2:
        copied = await relay_message(
            bot=bot,
            message=ordered_messages[0],
            destination_chat_id=destination_chat_id,
            destination_thread_id=destination_thread_id,
            user_id=user_id,
            source_side=source_side,
        )
        return (copied,)

    source_chat_id = ordered_messages[0].chat_id
    media_group_id = ordered_messages[0].media_group_id
    if not media_group_id or any(
        message.chat_id != source_chat_id
        or message.media_group_id != media_group_id
        for message in ordered_messages
    ):
        raise ValueError("相册消息必须来自同一聊天和 media_group_id")

    existing_mappings = [
        await _get_mapping(message, user_id, source_side)
        for message in ordered_messages
    ]
    if any(existing_mappings):
        if not all(existing_mappings) or any(
            mapping["user_id"] != user_id for mapping in existing_mappings
        ):
            raise ValueError("相册仅有部分消息已建立映射")
        return tuple(
            MessageId(_counterpart_id(mapping, source_side))
            for mapping in existing_mappings
        )

    reply_parameters = await _build_reply_parameters(
        ordered_messages[0],
        user_id,
        source_side,
    )
    if reply_parameters:
        media = [_editable_media(message) for message in ordered_messages]
        if any(
            item is None or isinstance(item, InputMediaAnimation)
            for item in media
        ):
            raise ValueError("该媒体组合不支持以相册回复格式发送")
        sent_messages = await _send_media_group_with_reply_fallback(
            bot=bot,
            media=media,
            destination_chat_id=destination_chat_id,
            destination_thread_id=destination_thread_id,
            reply_parameters=reply_parameters,
        )
        copied_messages = tuple(
            MessageId(message.message_id) for message in sent_messages
        )
    else:
        copied_messages = await bot.copy_messages(
            chat_id=destination_chat_id,
            from_chat_id=source_chat_id,
            message_ids=[message.message_id for message in ordered_messages],
            message_thread_id=destination_thread_id,
        )

    copied_messages = tuple(copied_messages)
    if len(copied_messages) != len(ordered_messages):
        if copied_messages:
            try:
                await bot.delete_messages(
                    destination_chat_id,
                    [message.message_id for message in copied_messages],
                )
            except Exception as cleanup_error:
                logger.error(
                    "相册返回数量异常后无法删除目标副本 %s: %s",
                    destination_chat_id,
                    cleanup_error,
                )
        raise RuntimeError("Telegram 返回的相册消息数量与源消息不一致")

    mappings = [
        _mapping_for_copy(
            message=message,
            copied_message_id=copied.message_id,
            destination_chat_id=destination_chat_id,
            destination_thread_id=destination_thread_id,
            user_id=user_id,
            source_side=source_side,
        )
        for message, copied in zip(ordered_messages, copied_messages)
    ]
    try:
        await db.save_message_mappings(mappings)
    except Exception:
        if await _mappings_are_persisted(mappings):
            logger.warning("相册映射保存返回错误，但读回确认已经提交")
            return tuple(copied_messages)
        try:
            await bot.delete_messages(
                destination_chat_id,
                [message.message_id for message in copied_messages],
            )
        except Exception as cleanup_error:
            logger.error(
                "相册映射保存失败后无法删除目标副本 %s: %s",
                destination_chat_id,
                cleanup_error,
            )
        raise

    return tuple(copied_messages)


def _is_message_not_modified(error: BadRequest) -> bool:
    return "message is not modified" in str(error).lower()


async def sync_edited_message(
    bot,
    message: Message,
    user_id: int,
    source_side: RelaySide,
) -> bool:
    mapping = await _get_mapping(message, user_id, source_side)
    if not mapping or mapping["user_id"] != user_id:
        return False

    destination_chat_id = (
        mapping["admin_chat_id"] if source_side == "user" else mapping["user_chat_id"]
    )
    destination_message_id = _counterpart_id(mapping, source_side)

    for attempt in range(len(_EDIT_RETRY_DELAYS) + 1):
        try:
            if message.text is not None:
                await bot.edit_message_text(
                    chat_id=destination_chat_id,
                    message_id=destination_message_id,
                    text=message.text,
                    entities=message.entities,
                    link_preview_options=message.link_preview_options,
                )
            else:
                media = _editable_media(message)
                if media:
                    await bot.edit_message_media(
                        chat_id=destination_chat_id,
                        message_id=destination_message_id,
                        media=media,
                    )
                elif message.voice or message.video_note:
                    await bot.edit_message_caption(
                        chat_id=destination_chat_id,
                        message_id=destination_message_id,
                        caption=message.caption,
                        caption_entities=message.caption_entities,
                        show_caption_above_media=message.show_caption_above_media,
                    )
                elif message.location:
                    location = message.location
                    if location.live_period is None:
                        await bot.stop_message_live_location(
                            chat_id=destination_chat_id,
                            message_id=destination_message_id,
                        )
                    else:
                        await bot.edit_message_live_location(
                            chat_id=destination_chat_id,
                            message_id=destination_message_id,
                            location=location,
                            horizontal_accuracy=location.horizontal_accuracy,
                            heading=location.heading,
                            proximity_alert_radius=location.proximity_alert_radius,
                            live_period=location.live_period,
                        )
                else:
                    return False
            return True
        except BadRequest as error:
            if _is_message_not_modified(error):
                return True
            logger.warning(
                "同步编辑失败 (%s:%s -> %s:%s): %s",
                message.chat_id,
                message.message_id,
                destination_chat_id,
                destination_message_id,
                error,
            )
            return False
        except RetryAfter as error:
            retry_after = error.retry_after
            retry_seconds = (
                retry_after.total_seconds()
                if hasattr(retry_after, "total_seconds")
                else float(retry_after)
            )
            if (
                attempt >= len(_EDIT_RETRY_DELAYS)
                or retry_seconds > _MAX_RETRY_AFTER_SECONDS
            ):
                logger.warning(
                    "同步编辑受到限流且无法及时重试 (%s:%s): %s",
                    message.chat_id,
                    message.message_id,
                    error,
                )
                return False
            await asyncio.sleep(max(0.0, retry_seconds))
        except NetworkError as error:
            if attempt >= len(_EDIT_RETRY_DELAYS):
                logger.warning(
                    "同步编辑在重试后仍失败 (%s:%s -> %s:%s): %s",
                    message.chat_id,
                    message.message_id,
                    destination_chat_id,
                    destination_message_id,
                    error,
                )
                return False
            await asyncio.sleep(_EDIT_RETRY_DELAYS[attempt])

    return False
