import asyncio
import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock

import pytest


def _stub_module(monkeypatch, name, **attributes):
    module = ModuleType(name)
    for attribute, value in attributes.items():
        setattr(module, attribute, value)
    monkeypatch.setitem(sys.modules, name, module)
    return module


def _load_callback_handler(monkeypatch):
    handlers_package = _stub_module(monkeypatch, "handlers")
    handlers_package.__path__ = []

    forward = AsyncMock()
    _stub_module(
        monkeypatch,
        "handlers.user_handler",
        _forward_verified_messages=forward,
    )
    verify = AsyncMock(
        return_value=(True, "verification passed", False, None, False)
    )
    _stub_module(
        monkeypatch,
        "services.verification",
        verify_answer=verify,
    )
    _stub_module(
        monkeypatch,
        "services.thread_manager",
        build_user_info_card_keyboard=AsyncMock(),
    )

    database_package = _stub_module(monkeypatch, "database")
    database_package.__path__ = []
    database_models = _stub_module(monkeypatch, "database.models")
    database_package.models = database_models

    rss_package = _stub_module(
        monkeypatch,
        "rss",
        data_manager=SimpleNamespace(),
        settings=SimpleNamespace(),
        enable_feature=lambda: None,
        disable_feature=lambda: None,
    )
    rss_package.__path__ = []

    module_path = Path(__file__).resolve().parents[1] / "handlers" / "callback_handler.py"
    spec = importlib.util.spec_from_file_location(
        "handlers.callback_handler_under_test",
        module_path,
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, verify, forward


class TaskRecordingApplication:
    def __init__(self):
        self.tasks = []

    def create_task(self, coroutine, **kwargs):
        task = asyncio.create_task(coroutine, name=kwargs.get("name"))
        self.tasks.append(task)
        return task


@pytest.mark.asyncio
async def test_successful_verification_forwards_all_pending_batches_in_order(monkeypatch):
    callback_handler, verify, forward = _load_callback_handler(monkeypatch)
    first_batch = [object()]
    second_batch = [object(), object()]
    third_batch = [object()]
    batches = [first_batch, second_batch, third_batch]
    query = SimpleNamespace(
        answer=AsyncMock(),
        data="verify:challenge-success:2",
        from_user=SimpleNamespace(id=42),
        edit_message_text=AsyncMock(),
        message=SimpleNamespace(reply_text=AsyncMock()),
    )
    update = SimpleNamespace(callback_query=query)
    context = SimpleNamespace(user_data={"pending_updates": batches})
    forwarded_batches = []
    forwarding = False

    async def record_forward(batch, forwarded_context, user_id):
        nonlocal forwarding
        assert forwarding is False
        forwarding = True
        await asyncio.sleep(0)
        forwarded_batches.append(batch)
        assert forwarded_context is context
        assert user_id == 42
        forwarding = False

    forward.side_effect = record_forward

    await callback_handler.handle_callback(update, context)

    verify.assert_awaited_once_with(42, "challenge-success", 2)
    assert forward.await_count == 3
    assert forwarded_batches == batches
    assert "pending_updates" not in context.user_data
    query.message.reply_text.assert_not_awaited()


@pytest.mark.asyncio
async def test_failed_batch_keeps_requeued_current_batch_and_unprocessed_tail(monkeypatch):
    callback_handler, _, forward = _load_callback_handler(monkeypatch)
    current_batch = [object()]
    second_batch = [object()]
    third_batch = [object()]
    requeued_current = [object()]
    context = SimpleNamespace(
        user_data={
            "pending_updates": [current_batch, second_batch, third_batch],
        },
    )

    async def fail_after_requeue(batch, forwarded_context, user_id):
        assert batch == current_batch
        assert user_id == 42
        forwarded_context.user_data["pending_updates"] = [requeued_current]
        return False

    forward.side_effect = fail_after_requeue

    forwarded = await callback_handler._forward_pending_batches(context, 42)

    assert forwarded is False
    assert context.user_data["pending_updates"] == [
        requeued_current,
        second_batch,
        third_batch,
    ]


@pytest.mark.asyncio
async def test_verification_callback_runs_through_real_async_serialized_queue(monkeypatch):
    callback_handler, verify, forward = _load_callback_handler(monkeypatch)
    application = TaskRecordingApplication()
    verification_started = asyncio.Event()
    release_verification = asyncio.Event()
    pending_batch = [object()]
    query = SimpleNamespace(
        answer=AsyncMock(),
        data="verify:challenge-queued:1",
        from_user=SimpleNamespace(id=42),
        edit_message_text=AsyncMock(),
        message=SimpleNamespace(reply_text=AsyncMock()),
    )
    update = SimpleNamespace(callback_query=query)
    context = SimpleNamespace(
        user_data={"pending_updates": [pending_batch]},
        bot_data={},
        application=application,
    )

    async def delayed_verification(user_id, challenge_id, option_index):
        assert (user_id, challenge_id, option_index) == (
            42,
            "challenge-queued",
            1,
        )
        verification_started.set()
        await release_verification.wait()
        return True, "verification passed", False, None, False

    verify.side_effect = delayed_verification

    await callback_handler.handle_callback(update, context)
    await asyncio.wait_for(verification_started.wait(), timeout=1)

    query.answer.assert_awaited_once()
    assert len(application.tasks) == 1
    assert application.tasks[0].done() is False
    forward.assert_not_awaited()

    release_verification.set()
    await asyncio.gather(*application.tasks)

    verify.assert_awaited_once_with(42, "challenge-queued", 1)
    forward.assert_awaited_once_with(pending_batch, context, 42)
    assert "pending_updates" not in context.user_data
    assert context.bot_data["message_relay_media_groups"] == {}
