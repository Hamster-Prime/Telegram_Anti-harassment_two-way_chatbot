import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from telegram import Chat, Message, Update, User

from services import media_group_buffer


class TaskRecordingApplication:
    def __init__(self):
        self.tasks = []

    def create_task(self, coroutine, **kwargs):
        task = asyncio.create_task(coroutine, name=kwargs.get("name"))
        self.tasks.append(task)
        return task


def _update(
    message_id,
    *,
    media_group_id=None,
    content=None,
    edited=False,
):
    message = Message(
        message_id=message_id,
        date=datetime.now(timezone.utc),
        chat=Chat(id=42, type=Chat.PRIVATE),
        from_user=User(id=42, first_name="Sender", is_bot=False),
        text=None if media_group_id else (content or f"item {message_id}"),
        caption=(content or f"item {message_id}") if media_group_id else None,
        media_group_id=media_group_id,
    )
    if edited:
        return Update(update_id=1000 + message_id, edited_message=message)
    return Update(update_id=message_id, message=message)


def _album_update(message_id):
    return _update(message_id, media_group_id="album-1")


async def _drain_tasks(application):
    drained = set()
    while True:
        pending = [task for task in application.tasks if task not in drained]
        if not pending:
            return
        await asyncio.gather(*pending)
        drained.update(pending)


@pytest.mark.asyncio
async def test_collect_media_group_flushes_once_with_sorted_unique_updates(monkeypatch):
    monkeypatch.setattr(media_group_buffer, "_SETTLE_SECONDS", 0)
    application = TaskRecordingApplication()
    context = SimpleNamespace(bot_data={}, application=application)
    callback = AsyncMock()
    update_3 = _album_update(3)
    update_1 = _album_update(1)
    replacement_1 = _album_update(1)
    update_2 = _album_update(2)

    for update in (update_3, update_1, replacement_1, update_2):
        await media_group_buffer.collect_media_group(
            update,
            context,
            scope="user",
            callback=callback,
        )

    assert len(application.tasks) == 1
    await asyncio.gather(*application.tasks)

    callback.assert_awaited_once()
    flushed_updates, flushed_context = callback.await_args.args
    assert [item.effective_message.message_id for item in flushed_updates] == [1, 2, 3]
    assert flushed_updates[0] is replacement_1
    assert flushed_context is context
    assert context.bot_data["message_relay_media_groups"] == {}


@pytest.mark.asyncio
async def test_enqueue_album_then_plain_message_preserves_callback_order(monkeypatch):
    monkeypatch.setattr(media_group_buffer, "_SETTLE_SECONDS", 0.01)
    application = TaskRecordingApplication()
    context = SimpleNamespace(bot_data={}, application=application)
    callback_batches = []

    async def callback(updates, callback_context):
        assert callback_context is context
        callback_batches.append(
            [update.effective_message.message_id for update in updates]
        )

    await media_group_buffer.enqueue_message(
        _update(2, media_group_id="album-a"),
        context,
        scope="user",
        callback=callback,
    )
    await media_group_buffer.enqueue_message(
        _update(1, media_group_id="album-a"),
        context,
        scope="user",
        callback=callback,
    )
    await media_group_buffer.enqueue_message(
        _update(3),
        context,
        scope="user",
        callback=callback,
    )

    await _drain_tasks(application)

    assert callback_batches == [[1, 2], [3]]


@pytest.mark.asyncio
async def test_two_albums_run_serially_in_first_enqueue_order(monkeypatch):
    monkeypatch.setattr(media_group_buffer, "_SETTLE_SECONDS", 0.01)
    application = TaskRecordingApplication()
    context = SimpleNamespace(bot_data={}, application=application)
    first_album_started = asyncio.Event()
    release_first_album = asyncio.Event()
    callback_batches = []
    active_callbacks = 0
    max_active_callbacks = 0

    async def callback(updates, callback_context):
        nonlocal active_callbacks, max_active_callbacks
        assert callback_context is context
        active_callbacks += 1
        max_active_callbacks = max(max_active_callbacks, active_callbacks)
        group_id = updates[0].effective_message.media_group_id
        callback_batches.append(group_id)
        if group_id == "album-a":
            first_album_started.set()
            await release_first_album.wait()
        active_callbacks -= 1

    for update in (
        _update(11, media_group_id="album-a"),
        _update(21, media_group_id="album-b"),
        _update(10, media_group_id="album-a"),
        _update(20, media_group_id="album-b"),
    ):
        await media_group_buffer.enqueue_message(
            update,
            context,
            scope="user",
            callback=callback,
        )

    await asyncio.wait_for(first_album_started.wait(), timeout=1)
    await asyncio.sleep(0.03)
    assert callback_batches == ["album-a"]

    release_first_album.set()
    await _drain_tasks(application)

    assert callback_batches == ["album-a", "album-b"]
    assert max_active_callbacks == 1


@pytest.mark.asyncio
async def test_replace_buffered_album_update_before_flush(monkeypatch):
    monkeypatch.setattr(media_group_buffer, "_SETTLE_SECONDS", 0.02)
    application = TaskRecordingApplication()
    context = SimpleNamespace(bot_data={}, application=application)
    flushed_batches = []

    async def callback(updates, callback_context):
        assert callback_context is context
        flushed_batches.append(updates)

    original = _update(31, media_group_id="album-a", content="old caption")
    sibling = _update(32, media_group_id="album-a")
    replacement = _update(
        31,
        media_group_id="album-a",
        content="new caption",
        edited=True,
    )
    await media_group_buffer.enqueue_message(
        original,
        context,
        scope="user",
        callback=callback,
    )
    await media_group_buffer.enqueue_message(
        sibling,
        context,
        scope="user",
        callback=callback,
    )

    replaced = media_group_buffer.replace_buffered_update(
        replacement,
        context,
        scope="user",
    )
    await _drain_tasks(application)

    assert replaced is True
    assert flushed_batches == [[replacement, sibling]]
    assert flushed_batches[0][0].effective_message.caption == "new caption"


@pytest.mark.asyncio
async def test_replace_buffered_plain_update_waiting_behind_album(monkeypatch):
    monkeypatch.setattr(media_group_buffer, "_SETTLE_SECONDS", 0.01)
    application = TaskRecordingApplication()
    context = SimpleNamespace(bot_data={}, application=application)
    first_callback_started = asyncio.Event()
    release_first_callback = asyncio.Event()
    flushed_batches = []

    async def callback(updates, callback_context):
        assert callback_context is context
        flushed_batches.append(updates)
        if updates[0].effective_message.media_group_id == "album-a":
            first_callback_started.set()
            await release_first_callback.wait()

    album = _update(41, media_group_id="album-a")
    original = _update(42, content="old text")
    replacement = _update(42, content="new text", edited=True)
    await media_group_buffer.enqueue_message(
        album,
        context,
        scope="user",
        callback=callback,
    )
    await media_group_buffer.enqueue_message(
        original,
        context,
        scope="user",
        callback=callback,
    )

    replaced = media_group_buffer.replace_buffered_update(
        replacement,
        context,
        scope="user",
    )
    await asyncio.wait_for(first_callback_started.wait(), timeout=1)
    release_first_callback.set()
    await _drain_tasks(application)

    assert replaced is True
    assert flushed_batches == [[album], [replacement]]
    assert flushed_batches[1][0].effective_message.text == "new text"


@pytest.mark.asyncio
async def test_plain_message_failure_notifies_sender_and_continues_queue():
    application = TaskRecordingApplication()
    bot = SimpleNamespace(send_message=AsyncMock())
    context = SimpleNamespace(
        bot=bot,
        bot_data={},
        application=application,
    )
    processed_message_ids = []

    async def callback(updates, callback_context):
        assert callback_context is context
        message_id = updates[0].effective_message.message_id
        processed_message_ids.append(message_id)
        if message_id == 51:
            raise RuntimeError("relay failed")

    await media_group_buffer.enqueue_message(
        _update(51),
        context,
        scope="user",
        callback=callback,
    )
    await media_group_buffer.enqueue_message(
        _update(52),
        context,
        scope="user",
        callback=callback,
    )

    await _drain_tasks(application)

    assert processed_message_ids == [51, 52]
    bot.send_message.assert_awaited_once()
    notification = bot.send_message.await_args.kwargs
    assert notification["chat_id"] == 42
    assert notification["message_thread_id"] is None
    assert notification["text"] == "这条消息未能完成传递，请稍后重新发送。"
    assert notification["reply_parameters"].message_id == 51
    assert notification["reply_parameters"].allow_sending_without_reply is True
    assert context.bot_data["message_relay_media_groups"] == {}
