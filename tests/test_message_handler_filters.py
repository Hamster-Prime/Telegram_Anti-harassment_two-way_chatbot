from datetime import datetime, timezone
import importlib
import sys
from types import ModuleType, SimpleNamespace

from telegram import (
    Chat,
    Invoice,
    Message,
    MessageEntity,
    PaidMediaInfo,
    PhotoSize,
    Update,
    User,
)
from telegram.ext import CommandHandler, MessageHandler

from config import config


class RecordingApplication:
    def __init__(self):
        self.handlers = []

    def add_handler(self, handler, *args, **kwargs):
        self.handlers.append(handler)


def _message(*, chat_id, chat_type, user_id, topic=False):
    return Message(
        message_id=10,
        date=datetime.now(timezone.utc),
        chat=Chat(id=chat_id, type=chat_type),
        from_user=User(id=user_id, first_name="Sender", is_bot=False),
        text="hello",
        message_thread_id=77 if topic else None,
        is_topic_message=topic,
    )


def _command_message(
    *,
    chat_id,
    chat_type,
    user_id,
    command="edited",
    topic=False,
):
    text = f"/{command}"
    message = Message(
        message_id=11,
        date=datetime.now(timezone.utc),
        chat=Chat(id=chat_id, type=chat_type),
        from_user=User(id=user_id, first_name="Sender", is_bot=False),
        text=text,
        entities=(MessageEntity(MessageEntity.BOT_COMMAND, 0, len(text)),),
        message_thread_id=77 if topic else None,
        is_topic_message=topic,
    )
    message.set_bot(SimpleNamespace(username="relaybot"))
    return message


def _attachment_message(*, attachment, chat_id=42, user_id=42):
    return Message(
        message_id=12,
        date=datetime.now(timezone.utc),
        chat=Chat(id=chat_id, type=Chat.PRIVATE),
        from_user=User(id=user_id, first_name="Sender", is_bot=False),
        **attachment,
    )


def _handler_by_callback(application, callback):
    return next(
        handler
        for handler in application.handlers
        if isinstance(handler, MessageHandler) and handler.callback is callback
    )


def _callback(name):
    async def callback(*args, **kwargs):
        return None

    callback.__name__ = name
    return callback


def _stub_module(monkeypatch, module_name, callback_names):
    module = ModuleType(module_name)
    for name in callback_names:
        setattr(module, name, _callback(name))
    monkeypatch.setitem(sys.modules, module_name, module)
    return module


def _load_handler_registration(monkeypatch):
    monkeypatch.delitem(sys.modules, "handlers", raising=False)
    command_module = _stub_module(
        monkeypatch,
        "handlers.command_handler",
        [
            "start",
            "help_command",
            "block",
            "unblock",
            "blacklist",
            "stats",
            "getid",
            "autoreply",
            "panel",
            "exempt",
        ],
    )
    user_module = _stub_module(
        monkeypatch,
        "handlers.user_handler",
        ["handle_edited_message", "handle_message"],
    )
    _stub_module(monkeypatch, "handlers.callback_handler", ["handle_callback"])
    admin_module = _stub_module(
        monkeypatch,
        "handlers.admin_handler",
        ["handle_admin_edit", "handle_admin_reply", "view_filtered"],
    )
    _stub_module(
        monkeypatch,
        "network_test.commands",
        [
            "ping_command",
            "nexttrace_command",
            "add_user_command",
            "rm_user_command",
            "add_server_command",
            "rm_server_command",
            "install_nexttrace_command",
        ],
    )
    handlers_module = importlib.import_module("handlers")
    return handlers_module, user_module, admin_module, command_module


def test_user_message_and_edited_message_handlers_are_disjoint(monkeypatch):
    monkeypatch.setattr(config, "FORUM_GROUP_ID", -100900)
    monkeypatch.setattr(config, "ADMIN_IDS", [9001])
    handlers_module, user_module, _, _ = _load_handler_registration(monkeypatch)
    application = RecordingApplication()
    handlers_module.register_handlers(application)
    normal_handler = _handler_by_callback(application, user_module.handle_message)
    edited_handler = _handler_by_callback(
        application,
        user_module.handle_edited_message,
    )
    message = _message(
        chat_id=42,
        chat_type=Chat.PRIVATE,
        user_id=42,
    )
    normal_update = Update(update_id=1, message=message)
    edited_update = Update(update_id=2, edited_message=message)

    assert bool(normal_handler.check_update(normal_update)) is True
    assert bool(normal_handler.check_update(edited_update)) is False
    assert bool(edited_handler.check_update(normal_update)) is False
    assert bool(edited_handler.check_update(edited_update)) is True


def test_admin_message_and_edited_message_handlers_are_disjoint(monkeypatch):
    monkeypatch.setattr(config, "FORUM_GROUP_ID", -100900)
    monkeypatch.setattr(config, "ADMIN_IDS", [9001])
    handlers_module, _, admin_module, _ = _load_handler_registration(monkeypatch)
    application = RecordingApplication()
    handlers_module.register_handlers(application)
    normal_handler = _handler_by_callback(
        application,
        admin_module.handle_admin_reply,
    )
    edited_handler = _handler_by_callback(
        application,
        admin_module.handle_admin_edit,
    )
    message = _message(
        chat_id=-100900,
        chat_type=Chat.SUPERGROUP,
        user_id=9001,
        topic=True,
    )
    normal_update = Update(update_id=3, message=message)
    edited_update = Update(update_id=4, edited_message=message)

    assert bool(normal_handler.check_update(normal_update)) is True
    assert bool(normal_handler.check_update(edited_update)) is False
    assert bool(edited_handler.check_update(normal_update)) is False
    assert bool(edited_handler.check_update(edited_update)) is True


def test_non_admin_forum_member_does_not_match_relay_handlers(monkeypatch):
    monkeypatch.setattr(config, "FORUM_GROUP_ID", -100900)
    monkeypatch.setattr(config, "ADMIN_IDS", [9001])
    handlers_module, _, admin_module, _ = _load_handler_registration(monkeypatch)
    application = RecordingApplication()
    handlers_module.register_handlers(application)
    normal_handler = _handler_by_callback(
        application,
        admin_module.handle_admin_reply,
    )
    edited_handler = _handler_by_callback(
        application,
        admin_module.handle_admin_edit,
    )
    message = _message(
        chat_id=-100900,
        chat_type=Chat.SUPERGROUP,
        user_id=9002,
        topic=True,
    )

    assert bool(
        normal_handler.check_update(Update(update_id=5, message=message))
    ) is False
    assert bool(
        edited_handler.check_update(Update(update_id=6, edited_message=message))
    ) is False


def test_edits_that_become_commands_still_reach_sync_handlers(monkeypatch):
    monkeypatch.setattr(config, "FORUM_GROUP_ID", -100900)
    monkeypatch.setattr(config, "ADMIN_IDS", [9001])
    handlers_module, user_module, admin_module, _ = _load_handler_registration(monkeypatch)
    application = RecordingApplication()
    handlers_module.register_handlers(application)
    user_edit = _handler_by_callback(
        application,
        user_module.handle_edited_message,
    )
    admin_edit = _handler_by_callback(
        application,
        admin_module.handle_admin_edit,
    )

    user_message = _command_message(
        chat_id=42,
        chat_type=Chat.PRIVATE,
        user_id=42,
    )
    admin_message = _command_message(
        chat_id=-100900,
        chat_type=Chat.SUPERGROUP,
        user_id=9001,
        topic=True,
    )

    assert bool(
        user_edit.check_update(Update(update_id=7, edited_message=user_message))
    ) is True
    assert bool(
        admin_edit.check_update(Update(update_id=8, edited_message=admin_message))
    ) is True


def test_known_commands_do_not_intercept_edited_messages(monkeypatch):
    monkeypatch.setattr(config, "FORUM_GROUP_ID", -100900)
    monkeypatch.setattr(config, "ADMIN_IDS", [9001])
    handlers_module, user_module, admin_module, _ = _load_handler_registration(monkeypatch)
    application = RecordingApplication()
    handlers_module.register_handlers(application)
    command_handlers = [
        handler
        for handler in application.handlers
        if isinstance(handler, CommandHandler)
    ]
    user_edit_handler = _handler_by_callback(
        application,
        user_module.handle_edited_message,
    )
    admin_edit_handler = _handler_by_callback(
        application,
        admin_module.handle_admin_edit,
    )
    updates = [
        Update(
            update_id=9,
            edited_message=_command_message(
                chat_id=42,
                chat_type=Chat.PRIVATE,
                user_id=42,
                command="start",
            ),
        ),
        Update(
            update_id=10,
            edited_message=_command_message(
                chat_id=-100900,
                chat_type=Chat.SUPERGROUP,
                user_id=9001,
                command="getid",
                topic=True,
            ),
        ),
    ]

    assert command_handlers
    for update in updates:
        assert all(
            not handler.check_update(update)
            for handler in command_handlers
        )
    assert bool(user_edit_handler.check_update(updates[0])) is True
    assert bool(admin_edit_handler.check_update(updates[1])) is True


def test_relay_filter_accepts_copyable_media_and_rejects_noncopyable_media(
    monkeypatch,
):
    monkeypatch.setattr(config, "FORUM_GROUP_ID", -100900)
    monkeypatch.setattr(config, "ADMIN_IDS", [9001])
    handlers_module, user_module, _, _ = _load_handler_registration(monkeypatch)
    application = RecordingApplication()
    handlers_module.register_handlers(application)
    user_handler = _handler_by_callback(
        application,
        user_module.handle_message,
    )
    photo = _attachment_message(
        attachment={
            "photo": (
                PhotoSize("photo-id", "photo-unique", 640, 480),
            ),
        },
    )
    invoice = _attachment_message(
        attachment={
            "invoice": Invoice(
                title="Invoice",
                description="Not copyable by Bot API",
                start_parameter="invoice-start",
                currency="USD",
                total_amount=100,
            ),
        },
    )
    paid_media = _attachment_message(
        attachment={
            "paid_media": PaidMediaInfo(star_count=1, paid_media=()),
        },
    )

    assert bool(user_handler.check_update(Update(update_id=11, message=photo))) is True
    assert bool(user_handler.check_update(Update(update_id=12, message=invoice))) is False
    assert bool(user_handler.check_update(Update(update_id=13, message=paid_media))) is False


def test_unknown_commands_fall_through_to_relay_handlers(monkeypatch):
    monkeypatch.setattr(config, "FORUM_GROUP_ID", -100900)
    monkeypatch.setattr(config, "ADMIN_IDS", [9001])
    handlers_module, user_module, admin_module, _ = _load_handler_registration(monkeypatch)
    application = RecordingApplication()
    handlers_module.register_handlers(application)
    command_handlers = [
        handler
        for handler in application.handlers
        if isinstance(handler, CommandHandler)
    ]
    user_relay = _handler_by_callback(application, user_module.handle_message)
    admin_relay = _handler_by_callback(application, admin_module.handle_admin_reply)
    user_update = Update(
        update_id=14,
        message=_command_message(
            chat_id=42,
            chat_type=Chat.PRIVATE,
            user_id=42,
            command="not_a_bot_command",
        ),
    )
    admin_update = Update(
        update_id=15,
        message=_command_message(
            chat_id=-100900,
            chat_type=Chat.SUPERGROUP,
            user_id=9001,
            command="not_a_bot_command",
            topic=True,
        ),
    )

    for update in (user_update, admin_update):
        assert all(not handler.check_update(update) for handler in command_handlers)
    assert bool(user_relay.check_update(user_update)) is True
    assert bool(admin_relay.check_update(admin_update)) is True


def test_rss_commands_only_intercept_new_private_messages(monkeypatch, tmp_path):
    monkeypatch.setitem(sys.modules, "feedparser", ModuleType("feedparser"))
    import rss

    callback = _callback("rss_list")
    application = RecordingApplication()
    application.bot_data = {}
    monkeypatch.setattr(rss.rss_handlers, "COMMAND_MAP", {"rss_list": callback})
    monkeypatch.setattr(
        rss.data_manager,
        "load_subscriptions",
        lambda data_file: None,
    )
    monkeypatch.setattr(
        rss.settings,
        "get_data_file",
        lambda: str(tmp_path / "rss.json"),
    )
    monkeypatch.setattr(rss.settings, "is_enabled", lambda: False)

    rss.setup(application)

    handler = next(
        item
        for item in application.handlers
        if isinstance(item, CommandHandler) and item.callback is callback
    )
    message = _command_message(
        chat_id=42,
        chat_type=Chat.PRIVATE,
        user_id=42,
        command="rss_list",
    )

    assert bool(handler.check_update(Update(update_id=16, message=message))) is True
    assert bool(
        handler.check_update(Update(update_id=17, edited_message=message))
    ) is False
