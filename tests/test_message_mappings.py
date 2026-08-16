import aiosqlite
import pytest

from database import models as db
from database.db_manager import DatabaseManager


async def _initialize_database(tmp_path, name="relay.sqlite3"):
    manager = DatabaseManager(tmp_path / name)
    await manager.initialize()
    return manager


async def _add_user(user_id=42):
    await db.add_user(
        user_id=user_id,
        username=f"user_{user_id}",
        first_name="Test User",
    )


@pytest.mark.asyncio
async def test_initialize_creates_message_mappings_table_and_indexes(tmp_path):
    manager = await _initialize_database(tmp_path)

    async with manager.get_connection() as connection:
        async with connection.execute("PRAGMA foreign_keys") as cursor:
            foreign_keys = (await cursor.fetchone())[0]
        async with connection.execute("PRAGMA busy_timeout") as cursor:
            busy_timeout = (await cursor.fetchone())[0]
        async with connection.execute("PRAGMA table_info(message_mappings)") as cursor:
            columns = {row[1]: row for row in await cursor.fetchall()}
        async with connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'index' "
            "AND tbl_name = 'message_mappings'"
        ) as cursor:
            indexes = {row[0] for row in await cursor.fetchall()}

    assert foreign_keys == 1
    assert busy_timeout == 5000
    assert {
        "id",
        "user_id",
        "user_chat_id",
        "user_message_id",
        "admin_chat_id",
        "admin_message_id",
        "thread_id",
        "origin_side",
        "created_at",
        "updated_at",
    } == set(columns)
    assert columns["user_chat_id"][3] == 1
    assert columns["admin_message_id"][3] == 1
    assert columns["thread_id"][3] == 1
    assert "idx_message_mappings_user" in indexes
    assert "idx_message_mappings_thread" in indexes


@pytest.mark.asyncio
async def test_message_mapping_can_be_queried_from_both_endpoints(tmp_path):
    await _initialize_database(tmp_path)
    await _add_user()

    saved = await db.save_message_mapping(
        user_id=42,
        user_chat_id=42,
        user_message_id=101,
        admin_chat_id=-100900,
        admin_message_id=501,
        thread_id=77,
        origin_side="user",
    )

    by_user = await db.get_message_mapping_by_user_endpoint(42, 101)
    by_admin = await db.get_message_mapping_by_admin_endpoint(-100900, 501)

    assert saved == by_user == by_admin
    assert by_user["user_id"] == 42
    assert by_user["thread_id"] == 77
    assert by_user["origin_side"] == "user"


@pytest.mark.asyncio
async def test_saving_identical_mapping_is_idempotent(tmp_path):
    manager = await _initialize_database(tmp_path)
    await _add_user()
    mapping = {
        "user_id": 42,
        "user_chat_id": 42,
        "user_message_id": 102,
        "admin_chat_id": -100900,
        "admin_message_id": 502,
        "thread_id": 77,
        "origin_side": "admin",
    }

    first = await db.save_message_mapping(**mapping)
    second = await db.save_message_mapping(**mapping)

    async with manager.get_connection() as connection:
        async with connection.execute(
            "SELECT COUNT(*) FROM message_mappings"
        ) as cursor:
            count = (await cursor.fetchone())[0]

    assert second == first
    assert count == 1


@pytest.mark.asyncio
async def test_conflicting_user_or_admin_endpoint_is_rejected(tmp_path):
    manager = await _initialize_database(tmp_path)
    await _add_user()
    original = {
        "user_id": 42,
        "user_chat_id": 42,
        "user_message_id": 103,
        "admin_chat_id": -100900,
        "admin_message_id": 503,
        "thread_id": 77,
        "origin_side": "user",
    }
    await db.save_message_mapping(**original)

    with pytest.raises(ValueError, match="already associated"):
        await db.save_message_mapping(
            **{
                **original,
                "admin_message_id": 504,
            }
        )

    with pytest.raises(ValueError, match="already associated"):
        await db.save_message_mapping(
            **{
                **original,
                "user_message_id": 104,
            }
        )

    async with manager.get_connection() as connection:
        async with connection.execute(
            "SELECT user_message_id, admin_message_id FROM message_mappings"
        ) as cursor:
            rows = await cursor.fetchall()

    assert rows == [(103, 503)]


@pytest.mark.asyncio
async def test_mapping_rejects_unknown_user(tmp_path):
    await _initialize_database(tmp_path)

    with pytest.raises(aiosqlite.IntegrityError, match="FOREIGN KEY constraint failed"):
        await db.save_message_mapping(
            user_id=404,
            user_chat_id=404,
            user_message_id=105,
            admin_chat_id=-100900,
            admin_message_id=505,
            thread_id=77,
            origin_side="user",
        )


@pytest.mark.asyncio
async def test_deleting_user_cascades_message_mappings(tmp_path):
    manager = await _initialize_database(tmp_path)
    await _add_user()
    await db.save_message_mapping(
        user_id=42,
        user_chat_id=42,
        user_message_id=106,
        admin_chat_id=-100900,
        admin_message_id=506,
        thread_id=77,
        origin_side="admin",
    )

    async with manager.get_connection() as connection:
        await connection.execute("DELETE FROM users WHERE user_id = ?", (42,))
        await connection.commit()

    assert await db.get_message_mapping_by_user_endpoint(42, 106) is None
    assert await db.get_message_mapping_by_admin_endpoint(-100900, 506) is None


@pytest.mark.asyncio
async def test_batch_save_rolls_back_when_later_mapping_violates_foreign_key(tmp_path):
    manager = await _initialize_database(tmp_path)
    await _add_user()
    mappings = [
        {
            "user_id": 42,
            "user_chat_id": 42,
            "user_message_id": 201,
            "admin_chat_id": -100900,
            "admin_message_id": 601,
            "thread_id": 77,
            "origin_side": "user",
        },
        {
            "user_id": 404,
            "user_chat_id": 404,
            "user_message_id": 202,
            "admin_chat_id": -100900,
            "admin_message_id": 602,
            "thread_id": 78,
            "origin_side": "user",
        },
    ]

    with pytest.raises(aiosqlite.IntegrityError, match="FOREIGN KEY constraint failed"):
        await db.save_message_mappings(mappings)

    async with manager.get_connection() as connection:
        async with connection.execute(
            "SELECT user_message_id, admin_message_id FROM message_mappings"
        ) as cursor:
            rows = await cursor.fetchall()

    assert rows == []


@pytest.mark.asyncio
async def test_batch_save_rolls_back_new_rows_on_existing_endpoint_conflict(tmp_path):
    manager = await _initialize_database(tmp_path)
    await _add_user()
    existing = {
        "user_id": 42,
        "user_chat_id": 42,
        "user_message_id": 203,
        "admin_chat_id": -100900,
        "admin_message_id": 603,
        "thread_id": 77,
        "origin_side": "user",
    }
    await db.save_message_mapping(**existing)

    new_mapping = {
        "user_id": 42,
        "user_chat_id": 42,
        "user_message_id": 204,
        "admin_chat_id": -100900,
        "admin_message_id": 604,
        "thread_id": 77,
        "origin_side": "admin",
    }
    conflicting = {
        **existing,
        "admin_message_id": 605,
    }

    with pytest.raises(ValueError, match="already associated"):
        await db.save_message_mappings([new_mapping, conflicting])

    async with manager.get_connection() as connection:
        async with connection.execute(
            "SELECT user_message_id, admin_message_id FROM message_mappings"
        ) as cursor:
            rows = await cursor.fetchall()

    assert rows == [(203, 603)]


@pytest.mark.asyncio
async def test_batch_save_returns_input_order_and_is_queryable_from_both_sides(tmp_path):
    manager = await _initialize_database(tmp_path)
    await _add_user()
    mappings = [
        {
            "user_id": 42,
            "user_chat_id": 42,
            "user_message_id": user_message_id,
            "admin_chat_id": -100900,
            "admin_message_id": admin_message_id,
            "thread_id": 77,
            "origin_side": origin_side,
        }
        for user_message_id, admin_message_id, origin_side in (
            (207, 607, "admin"),
            (205, 605, "user"),
            (206, 606, "user"),
        )
    ]

    saved = await db.save_message_mappings(mappings)
    repeated = await db.save_message_mappings(mappings)

    assert [row["user_message_id"] for row in saved] == [207, 205, 206]
    assert repeated == saved
    for expected, row in zip(mappings, saved):
        assert all(row[field] == value for field, value in expected.items())
        assert await db.get_message_mapping_by_user_endpoint(
            expected["user_chat_id"],
            expected["user_message_id"],
        ) == row
        assert await db.get_message_mapping_by_admin_endpoint(
            expected["admin_chat_id"],
            expected["admin_message_id"],
        ) == row

    async with manager.get_connection() as connection:
        async with connection.execute(
            "SELECT COUNT(*) FROM message_mappings"
        ) as cursor:
            count = (await cursor.fetchone())[0]

    assert count == len(mappings)


@pytest.mark.asyncio
async def test_batch_rejects_invalid_origin_before_writing_any_mapping(tmp_path):
    manager = await _initialize_database(tmp_path)
    await _add_user()
    valid = {
        "user_id": 42,
        "user_chat_id": 42,
        "user_message_id": 208,
        "admin_chat_id": -100900,
        "admin_message_id": 608,
        "thread_id": 77,
        "origin_side": "user",
    }

    with pytest.raises(ValueError, match="origin_side"):
        await db.save_message_mappings([
            valid,
            {
                **valid,
                "user_message_id": 209,
                "admin_message_id": 609,
                "origin_side": "unknown",
            },
        ])

    async with manager.get_connection() as connection:
        async with connection.execute(
            "SELECT COUNT(*) FROM message_mappings"
        ) as cursor:
            count = (await cursor.fetchone())[0]

    assert count == 0


@pytest.mark.asyncio
async def test_reset_user_relay_state_is_atomic_from_caller_perspective(tmp_path):
    await _initialize_database(tmp_path)
    await _add_user()
    await db.update_user_thread_id(42, 77)
    await db.update_user_verification(42, True)
    await db.save_message_mapping(
        user_id=42,
        user_chat_id=42,
        user_message_id=301,
        admin_chat_id=-100900,
        admin_message_id=701,
        thread_id=77,
        origin_side="user",
    )

    deleted = await db.reset_user_relay_state(42)

    user = await db.get_user(42)
    assert deleted == 1
    assert user["thread_id"] is None
    assert user["is_verified"] == 0
    assert await db.get_message_mapping_by_user_endpoint(42, 301) is None
