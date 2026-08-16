import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock

import pytest


@pytest.fixture
def verification(monkeypatch):
    gemini_module = ModuleType("services.gemini_service")
    gemini_module.gemini_service = SimpleNamespace(
        generate_verification_challenge=AsyncMock()
    )
    monkeypatch.setitem(sys.modules, "services.gemini_service", gemini_module)

    module_path = Path(__file__).resolve().parents[1] / "services" / "verification.py"
    spec = importlib.util.spec_from_file_location(
        "services.verification_under_test",
        module_path,
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    module.pending_verifications.clear()
    yield module
    module.pending_verifications.clear()


@pytest.mark.asyncio
async def test_stale_challenge_does_not_consume_attempt(
    monkeypatch,
    verification,
):
    challenges = [
        {
            "question": "first question",
            "correct_answer": "first correct",
            "options": ["first wrong", "first correct"],
        },
        {
            "question": "second question",
            "correct_answer": "second correct",
            "options": ["second correct", "second wrong"],
        },
    ]
    monkeypatch.setattr(
        verification.gemini_service,
        "generate_verification_challenge",
        AsyncMock(side_effect=challenges),
    )
    blacklist = AsyncMock()
    monkeypatch.setattr(verification.db, "add_to_blacklist", blacklist)

    _, first_keyboard = await verification.create_verification(42)
    first_data = first_keyboard.inline_keyboard[0][0].callback_data
    _, first_challenge_id, first_index = first_data.split(":")

    first_result = await verification.verify_answer(
        42,
        first_challenge_id,
        int(first_index),
    )
    current = verification.pending_verifications[42]
    attempts_after_first_answer = current["attempts"]

    stale_result = await verification.verify_answer(
        42,
        first_challenge_id,
        int(first_index),
    )

    assert first_result[0] is False
    assert first_result[3] is not None
    assert attempts_after_first_answer == 1
    assert stale_result[4] is True
    assert verification.pending_verifications[42] is current
    assert current["attempts"] == 1
    blacklist.assert_not_awaited()


@pytest.mark.asyncio
async def test_keyboard_uses_option_index_and_current_challenge_id(
    monkeypatch,
    verification,
):
    challenge = {
        "question": "choose",
        "correct_answer": "a very long answer with : and _",
        "options": ["a very long answer with : and _", "other"],
    }
    monkeypatch.setattr(
        verification.gemini_service,
        "generate_verification_challenge",
        AsyncMock(return_value=challenge),
    )
    update_verification = AsyncMock()
    monkeypatch.setattr(
        verification.db,
        "update_user_verification",
        update_verification,
    )

    _, keyboard = await verification.create_verification(42)
    callback_data = keyboard.inline_keyboard[0][0].callback_data
    _, challenge_id, option_index = callback_data.split(":")

    result = await verification.verify_answer(
        42,
        challenge_id,
        int(option_index),
    )

    assert len(callback_data.encode()) <= 64
    assert result[0] is True
    update_verification.assert_awaited_once_with(42, is_verified=True)
