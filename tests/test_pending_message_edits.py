from datetime import datetime, timezone
import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from telegram import (
    Chat,
    Message,
    MessageEntity,
    PhotoSize,
    ReplyParameters,
    Update,
    User,
)
from telegram.error import BadRequest, NetworkError


def _stub_module(monkeypatch, name, **attributes):
    module = ModuleType(name)
    for attribute, value in attributes.items():
        setattr(module, attribute, value)
    monkeypatch.setitem(sys.modules, name, module)


def _load_user_handler(monkeypatch):
    _stub_module(
        monkeypatch,
        "services.verification",
        create_verification=AsyncMock(),
        is_verification_pending=lambda user_id: (False, False),
        get_pending_verification_message=lambda user_id: None,
    )
    _stub_module(
        monkeypatch,
        "services.thread_manager",
        get_or_create_thread=AsyncMock(),
    )
    _stub_module(
        monkeypatch,
        "services.gemini_service",
        gemini_service=SimpleNamespace(),
    )
    _stub_module(
        monkeypatch,
        "utils.media_converter",
        sticker_to_image=AsyncMock(),
    )
    _stub_module(
        monkeypatch,
        "services.rate_limiter",
        rate_limiter=SimpleNamespace(),
    )

    module_path = Path(__file__).resolve().parents[1] / "handlers" / "user_handler.py"
    spec = importlib.util.spec_from_file_location(
        "tests.loaded_user_handler",
        module_path,
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _album_update(message_id, caption, *, edited=False):
    message = Message(
        message_id=message_id,
        date=datetime.now(timezone.utc),
        chat=Chat(id=42, type=Chat.PRIVATE),
        from_user=User(id=42, first_name="Sender", is_bot=False),
        photo=(PhotoSize(f"photo-{message_id}", f"unique-{message_id}", 10, 10),),
        caption=caption,
        media_group_id="pending-album",
    )
    if edited:
        return Update(update_id=1000 + message_id, edited_message=message)
    return Update(update_id=message_id, message=message)


def _pending_update(message_id, user, *, reply_text=None):
    message = SimpleNamespace(
        message_id=message_id,
        chat_id=user.id,
        reply_text=reply_text or AsyncMock(),
    )
    return SimpleNamespace(
        effective_message=message,
        effective_user=user,
    )


def _configure_unverified_user(monkeypatch, user_handler):
    monkeypatch.setattr(user_handler.config, "VERIFICATION_ENABLED", True)
    monkeypatch.setattr(
        user_handler.rate_limiter,
        "check_user_rate_limit",
        AsyncMock(return_value=(False, False)),
        raising=False,
    )
    monkeypatch.setattr(
        user_handler.db,
        "is_blacklisted",
        AsyncMock(return_value=(False, False)),
    )
    monkeypatch.setattr(
        user_handler.db,
        "get_user",
        AsyncMock(return_value={"is_verified": False}),
    )
    monkeypatch.setattr(
        user_handler.db,
        "update_user_profile",
        AsyncMock(),
    )
    monkeypatch.setattr(
        user_handler,
        "is_verification_pending",
        Mock(return_value=(True, False)),
    )
    monkeypatch.setattr(
        user_handler,
        "get_pending_verification_message",
        Mock(return_value=("verification question", object())),
    )


def _configure_autoreply(monkeypatch, user_handler, text="automatic answer"):
    monkeypatch.setattr(
        user_handler.db,
        "get_autoreply_enabled",
        AsyncMock(return_value=True),
    )
    monkeypatch.setattr(
        user_handler.db,
        "get_all_knowledge_content",
        AsyncMock(return_value="knowledge base"),
    )
    monkeypatch.setattr(
        user_handler.db,
        "save_message_mapping",
        AsyncMock(),
    )
    monkeypatch.setattr(
        user_handler.gemini_service,
        "generate_autoreply",
        AsyncMock(return_value=text),
        raising=False,
    )


def _autoreply_subject(reply_text):
    message = SimpleNamespace(
        message_id=101,
        chat_id=42,
        text="user question",
        reply_text=reply_text,
    )
    update = SimpleNamespace(effective_message=message)
    bot = SimpleNamespace(
        send_message=AsyncMock(
            return_value=SimpleNamespace(message_id=301),
        ),
        delete_message=AsyncMock(),
    )
    return message, update, SimpleNamespace(bot=bot)


def test_missing_thread_error_does_not_match_missing_source_message(monkeypatch):
    user_handler = _load_user_handler(monkeypatch)

    assert user_handler._is_missing_thread_error(
        BadRequest("Message thread not found")
    ) is True
    closed_error = BadRequest("Topic was closed")
    assert user_handler._is_missing_thread_error(closed_error) is False
    assert user_handler._is_closed_thread_error(closed_error) is True
    assert user_handler._is_missing_thread_error(
        BadRequest("Message to forward not found")
    ) is False
    assert user_handler._is_missing_thread_error(
        BadRequest("Message not found")
    ) is False


@pytest.mark.asyncio
async def test_autoreply_explicitly_replies_to_original_user_message(monkeypatch):
    user_handler = _load_user_handler(monkeypatch)
    _configure_autoreply(monkeypatch, user_handler, text="*automatic* answer")
    user_autoreply = SimpleNamespace(
        message_id=201,
        text="automatic answer",
        entities=(MessageEntity(MessageEntity.BOLD, 0, 9),),
    )
    reply_text = AsyncMock(return_value=user_autoreply)
    message, update, context = _autoreply_subject(reply_text)

    await user_handler._send_autoreply_if_enabled(
        update=update,
        context=context,
        user_id=42,
        thread_id=77,
        forwarded_message_id=501,
    )

    reply_text.assert_awaited_once()
    kwargs = reply_text.await_args.kwargs
    assert kwargs["parse_mode"] == "Markdown"
    assert isinstance(kwargs["reply_parameters"], ReplyParameters)
    assert kwargs["reply_parameters"].message_id == message.message_id
    assert kwargs["reply_parameters"].allow_sending_without_reply is True
    assert context.bot.send_message.await_args.kwargs["text"] == user_autoreply.text
    assert (
        context.bot.send_message.await_args.kwargs["entities"]
        == user_autoreply.entities
    )


@pytest.mark.asyncio
async def test_autoreply_bad_markdown_retries_once_as_plain_text(monkeypatch):
    user_handler = _load_user_handler(monkeypatch)
    _configure_autoreply(monkeypatch, user_handler)
    user_autoreply = SimpleNamespace(
        message_id=201,
        text="automatic answer",
        entities=(),
    )
    reply_text = AsyncMock(
        side_effect=[BadRequest("can't parse entities"), user_autoreply],
    )
    message, update, context = _autoreply_subject(reply_text)

    await user_handler._send_autoreply_if_enabled(
        update=update,
        context=context,
        user_id=42,
        thread_id=77,
        forwarded_message_id=501,
    )

    assert reply_text.await_count == 2
    markdown_call, plain_text_call = reply_text.await_args_list
    assert markdown_call.kwargs["parse_mode"] == "Markdown"
    assert "parse_mode" not in plain_text_call.kwargs
    for reply_call in (markdown_call, plain_text_call):
        parameters = reply_call.kwargs["reply_parameters"]
        assert parameters.message_id == message.message_id
        assert parameters.allow_sending_without_reply is True


@pytest.mark.asyncio
async def test_autoreply_network_error_is_not_retried_as_plain_text(monkeypatch):
    user_handler = _load_user_handler(monkeypatch)
    _configure_autoreply(monkeypatch, user_handler)
    reply_text = AsyncMock(side_effect=NetworkError("network unavailable"))
    _, update, context = _autoreply_subject(reply_text)

    with pytest.raises(NetworkError):
        await user_handler._send_autoreply_if_enabled(
            update=update,
            context=context,
            user_id=42,
            thread_id=77,
            forwarded_message_id=501,
        )

    assert reply_text.await_count == 1
    context.bot.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_unverified_messages_keep_every_arrival_as_an_ordered_batch(monkeypatch):
    user_handler = _load_user_handler(monkeypatch)
    _configure_unverified_user(monkeypatch, user_handler)
    user = SimpleNamespace(
        id=42,
        username="sender",
        first_name="Sender",
        last_name=None,
        language_code="zh-hans",
    )
    first = _pending_update(101, user)
    second = _pending_update(102, user)
    third = _pending_update(201, user)
    fourth = _pending_update(202, user)
    first_batch = [second, first]
    second_batch = [fourth, third]
    context = SimpleNamespace(user_data={}, bot=AsyncMock())

    await user_handler._handle_new_messages(first_batch, context)
    await user_handler._handle_new_messages(second_batch, context)

    assert context.user_data["pending_updates"] == [
        [first, second],
        [third, fourth],
    ]


@pytest.mark.asyncio
async def test_pre_verification_edit_replaces_matching_pending_album_update(monkeypatch):
    user_handler = _load_user_handler(monkeypatch)
    pending_first = _album_update(101, "first")
    pending_second = _album_update(102, "old caption")
    edited_second = _album_update(102, "new caption", edited=True)
    context = SimpleNamespace(
        user_data={"pending_updates": [[pending_first, pending_second]]},
        bot=AsyncMock(),
    )
    mapping_lookup = AsyncMock(return_value=None)
    monkeypatch.setattr(
        user_handler.db,
        "get_message_mapping_by_user_endpoint",
        mapping_lookup,
    )
    sync_edit = AsyncMock()
    monkeypatch.setattr(user_handler, "sync_edited_message", sync_edit)

    await user_handler.handle_edited_message(edited_second, context)

    pending = context.user_data["pending_updates"]
    assert pending == [[pending_first, edited_second]]
    assert pending[0][1].effective_message.caption == "new caption"
    mapping_lookup.assert_not_awaited()
    sync_edit.assert_not_awaited()


@pytest.mark.asyncio
async def test_pre_verification_edits_replace_only_their_exact_batch_items(monkeypatch):
    user_handler = _load_user_handler(monkeypatch)
    first = _album_update(101, "first")
    second = _album_update(102, "second old")
    third = _album_update(201, "third old")
    fourth = _album_update(202, "fourth")
    edited_second = _album_update(102, "second new", edited=True)
    edited_third = _album_update(201, "third new", edited=True)
    context = SimpleNamespace(
        user_data={"pending_updates": [[first, second], [third, fourth]]},
        bot=AsyncMock(),
    )
    mapping_lookup = AsyncMock(return_value=None)
    monkeypatch.setattr(
        user_handler.db,
        "get_message_mapping_by_user_endpoint",
        mapping_lookup,
    )
    sync_edit = AsyncMock()
    monkeypatch.setattr(user_handler, "sync_edited_message", sync_edit)

    await user_handler.handle_edited_message(edited_third, context)
    await user_handler.handle_edited_message(edited_second, context)

    assert context.user_data["pending_updates"] == [
        [first, edited_second],
        [edited_third, fourth],
    ]
    mapping_lookup.assert_not_awaited()
    sync_edit.assert_not_awaited()


@pytest.mark.asyncio
async def test_closed_topic_is_reopened_and_relay_retried(monkeypatch):
    user_handler = _load_user_handler(monkeypatch)
    user = SimpleNamespace(id=42)
    message = SimpleNamespace(
        message_id=101,
        chat_id=42,
        reply_text=AsyncMock(),
    )
    update = SimpleNamespace(effective_message=message, effective_user=user)
    context = SimpleNamespace(
        bot=SimpleNamespace(reopen_forum_topic=AsyncMock()),
        user_data={},
    )
    monkeypatch.setattr(
        user_handler,
        "_message_passes_moderation",
        AsyncMock(return_value=True),
    )
    monkeypatch.setattr(
        user_handler,
        "get_or_create_thread",
        AsyncMock(return_value=(77, False)),
    )
    resend = AsyncMock(
        side_effect=[
            BadRequest("TOPIC_CLOSED"),
            SimpleNamespace(message_id=501),
        ]
    )
    monkeypatch.setattr(user_handler, "_resend_message", resend)
    monkeypatch.setattr(
        user_handler,
        "_send_autoreply_if_enabled",
        AsyncMock(),
    )
    invalid_thread = AsyncMock()
    monkeypatch.setattr(user_handler, "handle_invalid_thread", invalid_thread)

    forwarded = await user_handler._forward_verified_messages(
        [update],
        context,
        42,
    )

    assert forwarded is True
    assert resend.await_count == 2
    context.bot.reopen_forum_topic.assert_awaited_once_with(
        chat_id=user_handler.config.FORUM_GROUP_ID,
        message_thread_id=77,
    )
    invalid_thread.assert_not_awaited()


@pytest.mark.asyncio
async def test_moderation_status_cleanup_failure_does_not_block_relay(monkeypatch):
    user_handler = _load_user_handler(monkeypatch)
    analyzing_message = SimpleNamespace(
        delete=AsyncMock(side_effect=NetworkError("delete failed")),
        edit_text=AsyncMock(),
    )
    context = SimpleNamespace(
        bot=SimpleNamespace(send_message=AsyncMock(return_value=analyzing_message)),
    )
    message = SimpleNamespace(
        message_id=101,
        chat_id=42,
        text="safe message",
        caption=None,
        photo=None,
        sticker=None,
    )
    monkeypatch.setattr(
        user_handler.db,
        "is_exempted",
        AsyncMock(return_value=False),
    )
    monkeypatch.setattr(
        user_handler.gemini_service,
        "analyze_message",
        AsyncMock(return_value={"is_spam": False}),
        raising=False,
    )

    passed = await user_handler._message_passes_moderation(
        message,
        context,
        42,
    )

    assert passed is True
    analyzing_message.delete.assert_awaited_once()


@pytest.mark.asyncio
async def test_verified_failed_batch_is_retained_for_next_attempt(monkeypatch):
    user_handler = _load_user_handler(monkeypatch)
    _stub_module(
        monkeypatch,
        "network_test.handlers",
        handle_message=AsyncMock(return_value=False),
    )
    user = SimpleNamespace(
        id=42,
        username="sender",
        first_name="Sender",
        last_name=None,
        language_code="zh-hans",
    )
    update = _pending_update(101, user)
    context = SimpleNamespace(user_data={}, bot=AsyncMock())
    monkeypatch.setattr(
        user_handler.rate_limiter,
        "check_user_rate_limit",
        AsyncMock(return_value=(False, False)),
        raising=False,
    )
    monkeypatch.setattr(
        user_handler.db,
        "is_blacklisted",
        AsyncMock(return_value=(False, False)),
    )
    monkeypatch.setattr(
        user_handler.db,
        "get_user",
        AsyncMock(return_value={"is_verified": True}),
    )
    monkeypatch.setattr(
        user_handler.db,
        "update_user_profile",
        AsyncMock(),
    )
    forward = AsyncMock(return_value=False)
    monkeypatch.setattr(user_handler, "_forward_verified_messages", forward)

    await user_handler._handle_new_messages([update], context)

    forward.assert_awaited_once_with([update], context, 42)
    assert context.user_data["pending_updates"] == [[update]]
