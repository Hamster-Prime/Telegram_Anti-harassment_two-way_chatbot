from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from telegram import (
    Animation,
    Audio,
    Chat,
    Document,
    InputMediaAnimation,
    InputMediaAudio,
    InputMediaDocument,
    InputMediaPhoto,
    InputMediaVideo,
    LinkPreviewOptions,
    Location,
    Message,
    MessageEntity,
    MessageId,
    PhotoSize,
    TextQuote,
    User,
    Video,
    Voice,
)
from telegram.error import BadRequest, NetworkError

from services import message_relay


USER_ID = 42
USER_CHAT_ID = 42
ADMIN_CHAT_ID = -100900
THREAD_ID = 77


def _message(
    *,
    chat_id,
    message_id,
    text=None,
    reply_to_message=None,
    quote=None,
    chat_type=Chat.PRIVATE,
    from_user_id=USER_ID,
    message_thread_id=None,
    is_topic_message=None,
    **kwargs,
):
    return Message(
        message_id=message_id,
        date=datetime.now(timezone.utc),
        chat=Chat(id=chat_id, type=chat_type),
        from_user=User(id=from_user_id, first_name="Sender", is_bot=False),
        text=text,
        reply_to_message=reply_to_message,
        quote=quote,
        message_thread_id=message_thread_id,
        is_topic_message=is_topic_message,
        **kwargs,
    )


def _mapping(
    *,
    user_message_id=101,
    admin_message_id=501,
    origin_side="user",
):
    return {
        "id": 1,
        "user_id": USER_ID,
        "user_chat_id": USER_CHAT_ID,
        "user_message_id": user_message_id,
        "admin_chat_id": ADMIN_CHAT_ID,
        "admin_message_id": admin_message_id,
        "thread_id": THREAD_ID,
        "origin_side": origin_side,
    }


@pytest.mark.asyncio
async def test_user_to_admin_reply_preserves_mapped_target_and_text_quote(monkeypatch):
    replied = _message(
        chat_id=USER_CHAT_ID,
        message_id=101,
        text="A\U0001f600quoted text",
    )
    quote_entity = MessageEntity(MessageEntity.BOLD, offset=0, length=6)
    source = _message(
        chat_id=USER_CHAT_ID,
        message_id=102,
        text="reply",
        reply_to_message=replied,
        quote=TextQuote(
            text="quoted",
            position=3,
            entities=(quote_entity,),
            is_manual=True,
        ),
    )
    lookup = AsyncMock(side_effect=[None, _mapping()])
    save = AsyncMock()
    monkeypatch.setattr(
        message_relay.db,
        "get_message_mapping_by_user_endpoint",
        lookup,
    )
    monkeypatch.setattr(message_relay.db, "save_message_mapping", save)
    bot = AsyncMock()
    bot.copy_message.return_value = MessageId(502)

    result = await message_relay.relay_message(
        bot=bot,
        message=source,
        destination_chat_id=ADMIN_CHAT_ID,
        destination_thread_id=THREAD_ID,
        user_id=USER_ID,
        source_side="user",
    )

    assert result.message_id == 502
    kwargs = bot.copy_message.await_args.kwargs
    assert kwargs["chat_id"] == ADMIN_CHAT_ID
    assert kwargs["from_chat_id"] == USER_CHAT_ID
    assert kwargs["message_id"] == 102
    assert kwargs["message_thread_id"] == THREAD_ID
    reply = kwargs["reply_parameters"]
    assert reply.message_id == 501
    assert reply.quote == "quoted"
    assert reply.quote_position == 3
    assert reply.quote_entities == (quote_entity,)
    assert reply.allow_sending_without_reply is True
    save.assert_awaited_once_with(
        user_id=USER_ID,
        user_chat_id=USER_CHAT_ID,
        user_message_id=102,
        admin_chat_id=ADMIN_CHAT_ID,
        admin_message_id=502,
        thread_id=THREAD_ID,
        origin_side="user",
    )


@pytest.mark.asyncio
async def test_admin_to_user_reply_uses_user_side_counterpart(monkeypatch):
    replied = _message(
        chat_id=ADMIN_CHAT_ID,
        message_id=501,
        text="mirrored user message",
        chat_type=Chat.SUPERGROUP,
        from_user_id=9000,
        message_thread_id=THREAD_ID,
        is_topic_message=True,
    )
    source = _message(
        chat_id=ADMIN_CHAT_ID,
        message_id=502,
        text="admin reply",
        reply_to_message=replied,
        chat_type=Chat.SUPERGROUP,
        from_user_id=9001,
        message_thread_id=THREAD_ID,
        is_topic_message=True,
    )
    lookup = AsyncMock(side_effect=[None, _mapping()])
    save = AsyncMock()
    monkeypatch.setattr(
        message_relay.db,
        "get_message_mapping_by_admin_endpoint",
        lookup,
    )
    monkeypatch.setattr(message_relay.db, "save_message_mapping", save)
    bot = AsyncMock()
    bot.copy_message.return_value = MessageId(103)

    await message_relay.relay_message(
        bot=bot,
        message=source,
        destination_chat_id=USER_CHAT_ID,
        user_id=USER_ID,
        source_side="admin",
    )

    kwargs = bot.copy_message.await_args.kwargs
    assert kwargs["chat_id"] == USER_CHAT_ID
    assert kwargs["from_chat_id"] == ADMIN_CHAT_ID
    assert kwargs["message_thread_id"] is None
    assert kwargs["reply_parameters"].message_id == 101
    save.assert_awaited_once_with(
        user_id=USER_ID,
        user_chat_id=USER_CHAT_ID,
        user_message_id=103,
        admin_chat_id=ADMIN_CHAT_ID,
        admin_message_id=502,
        thread_id=THREAD_ID,
        origin_side="admin",
    )


@pytest.mark.asyncio
async def test_unknown_reply_mapping_degrades_to_unthreaded_copy(monkeypatch):
    replied = _message(
        chat_id=USER_CHAT_ID,
        message_id=999,
        text="unmapped",
    )
    source = _message(
        chat_id=USER_CHAT_ID,
        message_id=104,
        text="reply",
        reply_to_message=replied,
    )
    monkeypatch.setattr(
        message_relay.db,
        "get_message_mapping_by_user_endpoint",
        AsyncMock(side_effect=[None, None]),
    )
    monkeypatch.setattr(
        message_relay.db,
        "save_message_mapping",
        AsyncMock(),
    )
    bot = AsyncMock()
    bot.copy_message.return_value = MessageId(504)

    await message_relay.relay_message(
        bot=bot,
        message=source,
        destination_chat_id=ADMIN_CHAT_ID,
        destination_thread_id=THREAD_ID,
        user_id=USER_ID,
        source_side="user",
    )

    assert bot.copy_message.await_count == 1
    assert bot.copy_message.await_args.kwargs["reply_parameters"] is None


@pytest.mark.asyncio
async def test_external_channel_reply_preserves_cross_chat_target(monkeypatch):
    external_chat = Chat(id=-100777, type=Chat.CHANNEL)
    source = _message(
        chat_id=USER_CHAT_ID,
        message_id=108,
        text="external reply",
        external_reply=SimpleNamespace(
            chat=external_chat,
            message_id=88,
        ),
        quote=TextQuote(text="channel quote", position=0),
    )
    monkeypatch.setattr(
        message_relay.db,
        "get_message_mapping_by_user_endpoint",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        message_relay.db,
        "save_message_mapping",
        AsyncMock(),
    )
    bot = AsyncMock()
    bot.copy_message.return_value = MessageId(508)

    copied = await message_relay.relay_message(
        bot=bot,
        message=source,
        destination_chat_id=ADMIN_CHAT_ID,
        destination_thread_id=THREAD_ID,
        user_id=USER_ID,
        source_side="user",
    )

    assert copied.message_id == 508
    reply = bot.copy_message.await_args.kwargs["reply_parameters"]
    assert reply.message_id == 88
    assert reply.chat_id == -100777
    assert reply.quote == "channel quote"
    assert reply.quote_position == 0
    assert reply.allow_sending_without_reply is not True


@pytest.mark.asyncio
async def test_invalid_quote_falls_back_to_plain_reply(monkeypatch):
    replied = _message(
        chat_id=USER_CHAT_ID,
        message_id=101,
        text="quoted text",
    )
    source = _message(
        chat_id=USER_CHAT_ID,
        message_id=105,
        text="reply",
        reply_to_message=replied,
        quote=TextQuote(text="quoted", position=0),
    )
    monkeypatch.setattr(
        message_relay.db,
        "get_message_mapping_by_user_endpoint",
        AsyncMock(side_effect=[None, _mapping()]),
    )
    monkeypatch.setattr(
        message_relay.db,
        "save_message_mapping",
        AsyncMock(),
    )
    bot = AsyncMock()
    bot.copy_message.side_effect = [BadRequest("quote not found"), MessageId(505)]

    result = await message_relay.relay_message(
        bot=bot,
        message=source,
        destination_chat_id=ADMIN_CHAT_ID,
        destination_thread_id=THREAD_ID,
        user_id=USER_ID,
        source_side="user",
    )

    assert result.message_id == 505
    assert bot.copy_message.await_count == 2
    first_reply = bot.copy_message.await_args_list[0].kwargs["reply_parameters"]
    second_reply = bot.copy_message.await_args_list[1].kwargs["reply_parameters"]
    assert first_reply.quote == "quoted"
    assert second_reply.message_id == 501
    assert second_reply.quote is None


@pytest.mark.asyncio
async def test_single_copy_is_deleted_when_mapping_save_fails(monkeypatch):
    source = _message(
        chat_id=USER_CHAT_ID,
        message_id=106,
        text="mapping will fail",
    )
    monkeypatch.setattr(
        message_relay.db,
        "get_message_mapping_by_user_endpoint",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        message_relay.db,
        "save_message_mapping",
        AsyncMock(side_effect=RuntimeError("database unavailable")),
    )
    bot = AsyncMock()
    bot.copy_message.return_value = MessageId(506)

    with pytest.raises(RuntimeError, match="database unavailable"):
        await message_relay.relay_message(
            bot=bot,
            message=source,
            destination_chat_id=ADMIN_CHAT_ID,
            destination_thread_id=THREAD_ID,
            user_id=USER_ID,
            source_side="user",
        )

    bot.delete_message.assert_awaited_once_with(ADMIN_CHAT_ID, 506)


@pytest.mark.asyncio
async def test_single_copy_is_kept_when_failed_save_was_committed(monkeypatch):
    source = _message(
        chat_id=USER_CHAT_ID,
        message_id=107,
        text="commit acknowledgement was lost",
    )
    persisted = _mapping(user_message_id=107, admin_message_id=507)
    monkeypatch.setattr(
        message_relay.db,
        "get_message_mapping_by_user_endpoint",
        AsyncMock(side_effect=[None, persisted]),
    )
    monkeypatch.setattr(
        message_relay.db,
        "get_message_mapping_by_admin_endpoint",
        AsyncMock(return_value=persisted),
    )
    monkeypatch.setattr(
        message_relay.db,
        "save_message_mapping",
        AsyncMock(side_effect=RuntimeError("commit acknowledgement lost")),
    )
    bot = AsyncMock()
    bot.copy_message.return_value = MessageId(507)

    copied = await message_relay.relay_message(
        bot=bot,
        message=source,
        destination_chat_id=ADMIN_CHAT_ID,
        destination_thread_id=THREAD_ID,
        user_id=USER_ID,
        source_side="user",
    )

    assert copied.message_id == 507
    bot.delete_message.assert_not_awaited()


def _album_photo(message_id, *, reply_to_message=None, quote=None):
    return _message(
        chat_id=USER_CHAT_ID,
        message_id=message_id,
        photo=(
            PhotoSize(
                f"photo-{message_id}",
                f"photo-unique-{message_id}",
                640,
                480,
            ),
        ),
        caption=f"caption {message_id}",
        media_group_id="album-1",
        reply_to_message=reply_to_message,
        quote=quote,
    )


@pytest.mark.asyncio
async def test_media_group_is_copied_in_order_and_saved_as_one_mapping_batch(
    monkeypatch,
):
    messages = [_album_photo(203), _album_photo(201), _album_photo(202)]
    lookup = AsyncMock(return_value=None)
    save = AsyncMock()
    monkeypatch.setattr(
        message_relay.db,
        "get_message_mapping_by_user_endpoint",
        lookup,
    )
    monkeypatch.setattr(message_relay.db, "save_message_mappings", save)
    bot = AsyncMock()
    bot.copy_messages.return_value = (
        MessageId(601),
        MessageId(602),
        MessageId(603),
    )

    copied = await message_relay.relay_media_group(
        bot=bot,
        messages=messages,
        destination_chat_id=ADMIN_CHAT_ID,
        destination_thread_id=THREAD_ID,
        user_id=USER_ID,
        source_side="user",
    )

    assert tuple(item.message_id for item in copied) == (601, 602, 603)
    bot.copy_messages.assert_awaited_once_with(
        chat_id=ADMIN_CHAT_ID,
        from_chat_id=USER_CHAT_ID,
        message_ids=[201, 202, 203],
        message_thread_id=THREAD_ID,
    )
    bot.send_media_group.assert_not_awaited()
    assert lookup.await_count == 3
    save.assert_awaited_once()
    mappings = save.await_args.args[0]
    assert [item["user_message_id"] for item in mappings] == [201, 202, 203]
    assert [item["admin_message_id"] for item in mappings] == [601, 602, 603]
    assert all(item["origin_side"] == "user" for item in mappings)


@pytest.mark.asyncio
async def test_media_group_reply_rebuilds_album_with_mapped_quote(monkeypatch):
    replied = _message(
        chat_id=USER_CHAT_ID,
        message_id=101,
        text="reply target",
    )
    quote_entity = MessageEntity(MessageEntity.BOLD, offset=0, length=6)
    first = _album_photo(
        231,
        reply_to_message=replied,
        quote=TextQuote(
            text="target",
            position=6,
            entities=(quote_entity,),
            is_manual=True,
        ),
    )
    second = _album_photo(232)
    lookup = AsyncMock(side_effect=[None, None, _mapping()])
    save = AsyncMock()
    monkeypatch.setattr(
        message_relay.db,
        "get_message_mapping_by_user_endpoint",
        lookup,
    )
    monkeypatch.setattr(message_relay.db, "save_message_mappings", save)
    bot = AsyncMock()
    bot.send_media_group.return_value = (MessageId(631), MessageId(632))

    copied = await message_relay.relay_media_group(
        bot=bot,
        messages=[second, first],
        destination_chat_id=ADMIN_CHAT_ID,
        destination_thread_id=THREAD_ID,
        user_id=USER_ID,
        source_side="user",
    )

    assert tuple(item.message_id for item in copied) == (631, 632)
    bot.copy_messages.assert_not_awaited()
    bot.send_media_group.assert_awaited_once()
    kwargs = bot.send_media_group.await_args.kwargs
    assert kwargs["chat_id"] == ADMIN_CHAT_ID
    assert kwargs["message_thread_id"] == THREAD_ID
    assert [item.caption for item in kwargs["media"]] == [
        "caption 231",
        "caption 232",
    ]
    assert all(isinstance(item, InputMediaPhoto) for item in kwargs["media"])
    reply = kwargs["reply_parameters"]
    assert reply.message_id == 501
    assert reply.quote == "target"
    assert reply.quote_position == 6
    assert reply.quote_entities == (quote_entity,)
    mappings = save.await_args.args[0]
    assert [item["user_message_id"] for item in mappings] == [231, 232]
    assert [item["admin_message_id"] for item in mappings] == [631, 632]


@pytest.mark.asyncio
async def test_media_group_copies_are_deleted_when_mapping_batch_save_fails(
    monkeypatch,
):
    messages = [_album_photo(211), _album_photo(212)]
    monkeypatch.setattr(
        message_relay.db,
        "get_message_mapping_by_user_endpoint",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        message_relay.db,
        "save_message_mappings",
        AsyncMock(side_effect=RuntimeError("batch mapping failed")),
    )
    bot = AsyncMock()
    bot.copy_messages.return_value = (MessageId(611), MessageId(612))

    with pytest.raises(RuntimeError, match="batch mapping failed"):
        await message_relay.relay_media_group(
            bot=bot,
            messages=messages,
            destination_chat_id=ADMIN_CHAT_ID,
            destination_thread_id=THREAD_ID,
            user_id=USER_ID,
            source_side="user",
        )

    bot.delete_messages.assert_awaited_once_with(
        ADMIN_CHAT_ID,
        [611, 612],
    )


@pytest.mark.asyncio
async def test_media_group_is_kept_when_failed_batch_save_was_committed(monkeypatch):
    messages = [_album_photo(213), _album_photo(214)]
    persisted = [
        _mapping(user_message_id=213, admin_message_id=613),
        _mapping(user_message_id=214, admin_message_id=614),
    ]
    monkeypatch.setattr(
        message_relay.db,
        "get_message_mapping_by_user_endpoint",
        AsyncMock(side_effect=[None, None, *persisted]),
    )
    monkeypatch.setattr(
        message_relay.db,
        "get_message_mapping_by_admin_endpoint",
        AsyncMock(side_effect=persisted),
    )
    monkeypatch.setattr(
        message_relay.db,
        "save_message_mappings",
        AsyncMock(side_effect=RuntimeError("commit acknowledgement lost")),
    )
    bot = AsyncMock()
    bot.copy_messages.return_value = (MessageId(613), MessageId(614))

    copied = await message_relay.relay_media_group(
        bot=bot,
        messages=messages,
        destination_chat_id=ADMIN_CHAT_ID,
        destination_thread_id=THREAD_ID,
        user_id=USER_ID,
        source_side="user",
    )

    assert tuple(item.message_id for item in copied) == (613, 614)
    bot.delete_messages.assert_not_awaited()


@pytest.mark.asyncio
async def test_partial_media_group_copy_is_deleted_and_never_mapped(monkeypatch):
    messages = [_album_photo(221), _album_photo(222), _album_photo(223)]
    monkeypatch.setattr(
        message_relay.db,
        "get_message_mapping_by_user_endpoint",
        AsyncMock(return_value=None),
    )
    save = AsyncMock()
    monkeypatch.setattr(message_relay.db, "save_message_mappings", save)
    bot = AsyncMock()
    bot.copy_messages.return_value = (MessageId(621), MessageId(622))

    with pytest.raises(RuntimeError, match="数量与源消息不一致"):
        await message_relay.relay_media_group(
            bot=bot,
            messages=messages,
            destination_chat_id=ADMIN_CHAT_ID,
            destination_thread_id=THREAD_ID,
            user_id=USER_ID,
            source_side="user",
        )

    bot.delete_messages.assert_awaited_once_with(
        ADMIN_CHAT_ID,
        [621, 622],
    )
    save.assert_not_awaited()


@pytest.mark.asyncio
async def test_text_edit_dispatches_to_mapped_admin_message(monkeypatch):
    entities = (MessageEntity(MessageEntity.ITALIC, offset=0, length=6),)
    preview = LinkPreviewOptions(is_disabled=True)
    source = _message(
        chat_id=USER_CHAT_ID,
        message_id=101,
        text="edited",
        entities=entities,
        link_preview_options=preview,
    )
    monkeypatch.setattr(
        message_relay.db,
        "get_message_mapping_by_user_endpoint",
        AsyncMock(return_value=_mapping()),
    )
    bot = AsyncMock()

    synced = await message_relay.sync_edited_message(
        bot=bot,
        message=source,
        user_id=USER_ID,
        source_side="user",
    )

    assert synced is True
    bot.edit_message_text.assert_awaited_once_with(
        chat_id=ADMIN_CHAT_ID,
        message_id=501,
        text="edited",
        entities=entities,
        link_preview_options=preview,
    )
    bot.edit_message_media.assert_not_awaited()
    bot.edit_message_caption.assert_not_awaited()


@pytest.mark.asyncio
async def test_text_edit_retries_network_error_then_succeeds(monkeypatch):
    monkeypatch.setattr(message_relay, "_EDIT_RETRY_DELAYS", (0, 0))
    source = _message(
        chat_id=USER_CHAT_ID,
        message_id=101,
        text="edited after retry",
    )
    monkeypatch.setattr(
        message_relay.db,
        "get_message_mapping_by_user_endpoint",
        AsyncMock(return_value=_mapping()),
    )
    bot = AsyncMock()
    bot.edit_message_text.side_effect = [
        NetworkError("temporary network failure"),
        None,
    ]

    synced = await message_relay.sync_edited_message(
        bot=bot,
        message=source,
        user_id=USER_ID,
        source_side="user",
    )

    assert synced is True
    assert bot.edit_message_text.await_count == 2
    assert bot.edit_message_text.await_args_list[0] == bot.edit_message_text.await_args_list[1]


@pytest.mark.asyncio
async def test_retry_message_not_modified_counts_as_success(monkeypatch):
    monkeypatch.setattr(message_relay, "_EDIT_RETRY_DELAYS", (0, 0))
    source = _message(
        chat_id=USER_CHAT_ID,
        message_id=101,
        text="possibly applied before disconnect",
    )
    monkeypatch.setattr(
        message_relay.db,
        "get_message_mapping_by_user_endpoint",
        AsyncMock(return_value=_mapping()),
    )
    bot = AsyncMock()
    bot.edit_message_text.side_effect = [
        NetworkError("connection lost after request"),
        BadRequest("Message is not modified"),
    ]

    synced = await message_relay.sync_edited_message(
        bot=bot,
        message=source,
        user_id=USER_ID,
        source_side="user",
    )

    assert synced is True
    assert bot.edit_message_text.await_count == 2


@pytest.mark.asyncio
async def test_text_edit_returns_false_after_network_retries_are_exhausted(monkeypatch):
    monkeypatch.setattr(message_relay, "_EDIT_RETRY_DELAYS", (0, 0))
    source = _message(
        chat_id=USER_CHAT_ID,
        message_id=101,
        text="never delivered",
    )
    monkeypatch.setattr(
        message_relay.db,
        "get_message_mapping_by_user_endpoint",
        AsyncMock(return_value=_mapping()),
    )
    bot = AsyncMock()
    bot.edit_message_text.side_effect = NetworkError("network unavailable")

    synced = await message_relay.sync_edited_message(
        bot=bot,
        message=source,
        user_id=USER_ID,
        source_side="user",
    )

    assert synced is False
    assert bot.edit_message_text.await_count == 3


@pytest.mark.asyncio
async def test_unmapped_edit_returns_false_without_editing(monkeypatch):
    source = _message(
        chat_id=USER_CHAT_ID,
        message_id=999,
        text="edited but unmapped",
    )
    monkeypatch.setattr(
        message_relay.db,
        "get_message_mapping_by_user_endpoint",
        AsyncMock(return_value=None),
    )
    bot = AsyncMock()

    synced = await message_relay.sync_edited_message(
        bot=bot,
        message=source,
        user_id=USER_ID,
        source_side="user",
    )

    assert synced is False
    bot.edit_message_text.assert_not_awaited()
    bot.edit_message_media.assert_not_awaited()
    bot.edit_message_caption.assert_not_awaited()
    bot.edit_message_live_location.assert_not_awaited()


@pytest.mark.asyncio
async def test_admin_text_edit_dispatches_to_mapped_user_message(monkeypatch):
    source = _message(
        chat_id=ADMIN_CHAT_ID,
        message_id=502,
        text="edited by admin",
        chat_type=Chat.SUPERGROUP,
        from_user_id=9001,
        message_thread_id=THREAD_ID,
        is_topic_message=True,
    )
    monkeypatch.setattr(
        message_relay.db,
        "get_message_mapping_by_admin_endpoint",
        AsyncMock(return_value=_mapping(admin_message_id=502)),
    )
    bot = AsyncMock()

    synced = await message_relay.sync_edited_message(
        bot=bot,
        message=source,
        user_id=USER_ID,
        source_side="admin",
    )

    assert synced is True
    bot.edit_message_text.assert_awaited_once_with(
        chat_id=USER_CHAT_ID,
        message_id=101,
        text="edited by admin",
        entities=source.entities,
        link_preview_options=source.link_preview_options,
    )


@pytest.mark.asyncio
async def test_live_location_edit_preserves_all_dynamic_fields(monkeypatch):
    location = Location(
        longitude=120.5,
        latitude=30.25,
        horizontal_accuracy=12.5,
        live_period=900,
        heading=180,
        proximity_alert_radius=75,
    )
    source = _message(
        chat_id=USER_CHAT_ID,
        message_id=101,
        location=location,
    )
    monkeypatch.setattr(
        message_relay.db,
        "get_message_mapping_by_user_endpoint",
        AsyncMock(return_value=_mapping()),
    )
    bot = AsyncMock()

    synced = await message_relay.sync_edited_message(
        bot=bot,
        message=source,
        user_id=USER_ID,
        source_side="user",
    )

    assert synced is True
    bot.edit_message_live_location.assert_awaited_once_with(
        chat_id=ADMIN_CHAT_ID,
        message_id=501,
        location=location,
        horizontal_accuracy=12.5,
        heading=180,
        proximity_alert_radius=75,
        live_period=900,
    )


@pytest.mark.asyncio
async def test_stopped_live_location_stops_counterpart(monkeypatch):
    source = _message(
        chat_id=USER_CHAT_ID,
        message_id=101,
        location=Location(longitude=120.5, latitude=30.25),
    )
    monkeypatch.setattr(
        message_relay.db,
        "get_message_mapping_by_user_endpoint",
        AsyncMock(return_value=_mapping()),
    )
    bot = AsyncMock()

    synced = await message_relay.sync_edited_message(
        bot=bot,
        message=source,
        user_id=USER_ID,
        source_side="user",
    )

    assert synced is True
    bot.stop_message_live_location.assert_awaited_once_with(
        chat_id=ADMIN_CHAT_ID,
        message_id=501,
    )
    bot.edit_message_live_location.assert_not_awaited()


def _photo_message():
    return _message(
        chat_id=USER_CHAT_ID,
        message_id=101,
        photo=(PhotoSize("photo-id", "photo-unique", 640, 480),),
        caption="photo caption",
        caption_entities=(MessageEntity(MessageEntity.BOLD, 0, 5),),
        has_media_spoiler=True,
        show_caption_above_media=True,
    )


def _video_message():
    return _message(
        chat_id=USER_CHAT_ID,
        message_id=101,
        video=Video("video-id", "video-unique", 640, 480, 12),
        caption="video caption",
    )


@pytest.mark.asyncio
async def test_video_edit_preserves_cover_and_start_timestamp(monkeypatch):
    cover = (
        PhotoSize("cover-small", "cover-small-unique", 160, 90),
        PhotoSize("cover-large", "cover-large-unique", 1280, 720),
    )
    source = _message(
        chat_id=USER_CHAT_ID,
        message_id=101,
        video=Video(
            "video-id",
            "video-unique",
            1280,
            720,
            30,
            cover=cover,
            start_timestamp=8,
        ),
        caption="video caption",
    )
    monkeypatch.setattr(
        message_relay.db,
        "get_message_mapping_by_user_endpoint",
        AsyncMock(return_value=_mapping()),
    )
    bot = AsyncMock()

    synced = await message_relay.sync_edited_message(
        bot=bot,
        message=source,
        user_id=USER_ID,
        source_side="user",
    )

    assert synced is True
    media = bot.edit_message_media.await_args.kwargs["media"]
    assert isinstance(media, InputMediaVideo)
    assert media.cover == "cover-large"
    assert media.start_timestamp == 8


def _animation_message():
    return _message(
        chat_id=USER_CHAT_ID,
        message_id=101,
        animation=Animation("animation-id", "animation-unique", 320, 240, 4),
        caption="animation caption",
    )


def _audio_message():
    return _message(
        chat_id=USER_CHAT_ID,
        message_id=101,
        audio=Audio(
            "audio-id",
            "audio-unique",
            30,
            performer="Artist",
            title="Title",
        ),
        caption="audio caption",
    )


def _document_message():
    return _message(
        chat_id=USER_CHAT_ID,
        message_id=101,
        document=Document("document-id", "document-unique", file_name="file.txt"),
        caption="document caption",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("message_factory", "expected_type", "expected_file_id"),
    [
        (_photo_message, InputMediaPhoto, "photo-id"),
        (_video_message, InputMediaVideo, "video-id"),
        (_animation_message, InputMediaAnimation, "animation-id"),
        (_audio_message, InputMediaAudio, "audio-id"),
        (_document_message, InputMediaDocument, "document-id"),
    ],
)
async def test_editable_media_dispatches_as_input_media(
    monkeypatch,
    message_factory,
    expected_type,
    expected_file_id,
):
    monkeypatch.setattr(
        message_relay.db,
        "get_message_mapping_by_user_endpoint",
        AsyncMock(return_value=_mapping()),
    )
    bot = AsyncMock()

    synced = await message_relay.sync_edited_message(
        bot=bot,
        message=message_factory(),
        user_id=USER_ID,
        source_side="user",
    )

    assert synced is True
    bot.edit_message_media.assert_awaited_once()
    kwargs = bot.edit_message_media.await_args.kwargs
    assert kwargs["chat_id"] == ADMIN_CHAT_ID
    assert kwargs["message_id"] == 501
    assert isinstance(kwargs["media"], expected_type)
    assert kwargs["media"].media == expected_file_id
    bot.edit_message_text.assert_not_awaited()


@pytest.mark.asyncio
async def test_voice_caption_edit_dispatches_to_edit_message_caption(monkeypatch):
    source = _message(
        chat_id=ADMIN_CHAT_ID,
        message_id=502,
        chat_type=Chat.SUPERGROUP,
        from_user_id=9001,
        message_thread_id=THREAD_ID,
        is_topic_message=True,
        voice=Voice("voice-id", "voice-unique", 5),
        caption="new caption",
        caption_entities=(MessageEntity(MessageEntity.UNDERLINE, 0, 3),),
    )
    monkeypatch.setattr(
        message_relay.db,
        "get_message_mapping_by_admin_endpoint",
        AsyncMock(return_value=_mapping(admin_message_id=502)),
    )
    bot = AsyncMock()

    synced = await message_relay.sync_edited_message(
        bot=bot,
        message=source,
        user_id=USER_ID,
        source_side="admin",
    )

    assert synced is True
    bot.edit_message_caption.assert_awaited_once_with(
        chat_id=USER_CHAT_ID,
        message_id=101,
        caption="new caption",
        caption_entities=source.caption_entities,
        show_caption_above_media=source.show_caption_above_media,
    )
