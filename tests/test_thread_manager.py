from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from config import config
from services import thread_manager


@pytest.mark.asyncio
async def test_new_topic_is_deleted_when_database_mapping_fails(monkeypatch):
    user = SimpleNamespace(
        id=42,
        first_name="Test",
        last_name=None,
        username=None,
    )
    update = SimpleNamespace(effective_user=user)
    bot = SimpleNamespace(
        create_forum_topic=AsyncMock(
            return_value=SimpleNamespace(message_thread_id=77)
        ),
        delete_forum_topic=AsyncMock(),
        close_forum_topic=AsyncMock(),
    )
    context = SimpleNamespace(bot=bot)
    monkeypatch.setattr(thread_manager.db, "get_user", AsyncMock(return_value=None))
    monkeypatch.setattr(
        thread_manager.db,
        "update_user_thread_id",
        AsyncMock(side_effect=RuntimeError("database unavailable")),
    )
    info_card = AsyncMock()
    monkeypatch.setattr(thread_manager, "send_user_info_card", info_card)

    result = await thread_manager.get_or_create_thread(update, context)

    assert result == (None, False)
    bot.delete_forum_topic.assert_awaited_once_with(
        chat_id=config.FORUM_GROUP_ID,
        message_thread_id=77,
    )
    bot.close_forum_topic.assert_not_awaited()
    info_card.assert_not_awaited()


@pytest.mark.asyncio
async def test_info_card_failure_keeps_persisted_topic(monkeypatch):
    user = SimpleNamespace(
        id=42,
        first_name="Test",
        last_name=None,
        username=None,
    )
    update = SimpleNamespace(effective_user=user)
    bot = SimpleNamespace(
        create_forum_topic=AsyncMock(
            return_value=SimpleNamespace(message_thread_id=77)
        ),
        delete_forum_topic=AsyncMock(),
        close_forum_topic=AsyncMock(),
    )
    context = SimpleNamespace(bot=bot)
    save_thread = AsyncMock()
    monkeypatch.setattr(thread_manager.db, "get_user", AsyncMock(return_value=None))
    monkeypatch.setattr(thread_manager.db, "update_user_thread_id", save_thread)
    monkeypatch.setattr(
        thread_manager,
        "send_user_info_card",
        AsyncMock(side_effect=RuntimeError("telegram unavailable")),
    )

    result = await thread_manager.get_or_create_thread(update, context)

    assert result == (77, True)
    save_thread.assert_awaited_once_with(42, 77)
    bot.delete_forum_topic.assert_not_awaited()


@pytest.mark.asyncio
async def test_committed_topic_is_kept_when_database_call_reports_failure(monkeypatch):
    user = SimpleNamespace(
        id=42,
        first_name="Test",
        last_name=None,
        username=None,
    )
    update = SimpleNamespace(effective_user=user)
    bot = SimpleNamespace(
        create_forum_topic=AsyncMock(
            return_value=SimpleNamespace(message_thread_id=77)
        ),
        delete_forum_topic=AsyncMock(),
        close_forum_topic=AsyncMock(),
    )
    context = SimpleNamespace(bot=bot)
    get_user = AsyncMock(side_effect=[None, {"thread_id": 77}])
    monkeypatch.setattr(thread_manager.db, "get_user", get_user)
    monkeypatch.setattr(
        thread_manager.db,
        "update_user_thread_id",
        AsyncMock(side_effect=RuntimeError("commit acknowledgement lost")),
    )
    monkeypatch.setattr(thread_manager, "send_user_info_card", AsyncMock())

    result = await thread_manager.get_or_create_thread(update, context)

    assert result == (77, True)
    assert get_user.await_count == 2
    bot.delete_forum_topic.assert_not_awaited()
    bot.close_forum_topic.assert_not_awaited()


@pytest.mark.asyncio
async def test_failed_topic_delete_falls_back_to_close(monkeypatch):
    user = SimpleNamespace(
        id=42,
        first_name="Test",
        last_name=None,
        username=None,
    )
    update = SimpleNamespace(effective_user=user)
    bot = SimpleNamespace(
        create_forum_topic=AsyncMock(
            return_value=SimpleNamespace(message_thread_id=77)
        ),
        delete_forum_topic=AsyncMock(side_effect=RuntimeError("no delete permission")),
        close_forum_topic=AsyncMock(),
    )
    context = SimpleNamespace(bot=bot)
    monkeypatch.setattr(
        thread_manager.db,
        "get_user",
        AsyncMock(side_effect=[None, {"thread_id": None}]),
    )
    monkeypatch.setattr(
        thread_manager.db,
        "update_user_thread_id",
        AsyncMock(side_effect=RuntimeError("database unavailable")),
    )
    monkeypatch.setattr(thread_manager, "send_user_info_card", AsyncMock())

    result = await thread_manager.get_or_create_thread(update, context)

    assert result == (None, False)
    bot.close_forum_topic.assert_awaited_once_with(
        chat_id=config.FORUM_GROUP_ID,
        message_thread_id=77,
    )
