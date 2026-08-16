import pytest

from database import models as db
from database.db_manager import DatabaseManager


async def _initialize_database(tmp_path):
    manager = DatabaseManager(tmp_path / "foreign-keys.sqlite3")
    await manager.initialize()
    return manager


@pytest.mark.asyncio
async def test_add_to_blacklist_creates_unknown_user_with_foreign_keys_enabled(tmp_path):
    manager = await _initialize_database(tmp_path)

    await db.add_to_blacklist(
        user_id=9101,
        reason="test block",
        blocked_by=7001,
        permanent=True,
    )

    async with manager.get_connection() as connection:
        async with connection.execute("PRAGMA foreign_keys") as cursor:
            foreign_keys = (await cursor.fetchone())[0]
        async with connection.execute(
            "SELECT first_name, is_blacklisted, blacklist_strikes "
            "FROM users WHERE user_id = ?",
            (9101,),
        ) as cursor:
            user = await cursor.fetchone()
        async with connection.execute(
            "SELECT reason, blocked_by, permanent FROM blacklist WHERE user_id = ?",
            (9101,),
        ) as cursor:
            blacklist_entry = await cursor.fetchone()

    assert foreign_keys == 1
    assert user == ("User_9101", 1, 1)
    assert blacklist_entry == ("test block", 7001, 1)


@pytest.mark.asyncio
async def test_add_exemption_creates_unknown_user_with_foreign_keys_enabled(tmp_path):
    manager = await _initialize_database(tmp_path)

    await db.add_exemption(
        user_id=9102,
        is_permanent=True,
        exempted_by=7001,
        reason="test exemption",
    )

    async with manager.get_connection() as connection:
        async with connection.execute("PRAGMA foreign_keys") as cursor:
            foreign_keys = (await cursor.fetchone())[0]
        async with connection.execute(
            "SELECT first_name FROM users WHERE user_id = ?",
            (9102,),
        ) as cursor:
            user = await cursor.fetchone()
        async with connection.execute(
            "SELECT is_permanent, exempted_by, reason "
            "FROM exemptions WHERE user_id = ?",
            (9102,),
        ) as cursor:
            exemption = await cursor.fetchone()

    assert foreign_keys == 1
    assert user == ("User_9102",)
    assert exemption == (1, 7001, "test exemption")
