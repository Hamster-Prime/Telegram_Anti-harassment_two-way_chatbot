from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters
from .command_handler import start, help_command, block, unblock, blacklist, stats, getid, autoreply, panel, exempt
from .user_handler import handle_edited_message, handle_message
from .callback_handler import handle_callback
from .admin_handler import handle_admin_edit, handle_admin_reply, view_filtered
from config import config
from network_test.commands import (
    ping_command, nexttrace_command, add_user_command, rm_user_command,
    add_server_command, rm_server_command, install_nexttrace_command
)

def register_handlers(app: Application):
    new_message = filters.UpdateType.MESSAGE
    app.add_handler(CommandHandler("getid", getid, filters=new_message))
    app.add_handler(CommandHandler(
        "start",
        start,
        filters=new_message & filters.ChatType.PRIVATE,
    ))
    
    app.add_handler(CommandHandler("ping", ping_command, filters=new_message))
    app.add_handler(CommandHandler("nexttrace", nexttrace_command, filters=new_message))
    app.add_handler(CommandHandler("adduser", add_user_command, filters=new_message))
    app.add_handler(CommandHandler("rmuser", rm_user_command, filters=new_message))
    app.add_handler(CommandHandler("addserver", add_server_command, filters=new_message))
    app.add_handler(CommandHandler("rmserver", rm_server_command, filters=new_message))
    app.add_handler(CommandHandler(
        "install_nexttrace",
        install_nexttrace_command,
        filters=new_message,
    ))

    if config.FORUM_GROUP_ID and config.ADMIN_IDS:
        relayable_content = (
            filters.TEXT
            | filters.ANIMATION
            | filters.AUDIO
            | filters.CONTACT
            | filters.Dice.ALL
            | filters.Document.ALL
            | filters.GAME
            | filters.LOCATION
            | filters.PHOTO
            | filters.POLL
            | filters.Sticker.ALL
            | filters.STORY
            | filters.VENUE
            | filters.VIDEO
            | filters.VIDEO_NOTE
            | filters.VOICE
        )
        admin_chat = filters.Chat(chat_id=config.FORUM_GROUP_ID)
        configured_admin = filters.User(user_id=config.ADMIN_IDS)

        app.add_handler(CommandHandler(
            "help",
            help_command,
            filters=new_message & filters.ChatType.PRIVATE,
        ))
        app.add_handler(CommandHandler("block", block, filters=new_message))
        app.add_handler(CommandHandler("unblock", unblock, filters=new_message))
        app.add_handler(CommandHandler("panel", panel, filters=new_message))
        app.add_handler(CommandHandler("blacklist", blacklist, filters=new_message))
        app.add_handler(CommandHandler("stats", stats, filters=new_message))
        app.add_handler(CommandHandler(
            "view_filtered",
            view_filtered,
            filters=new_message,
        ))
        app.add_handler(CommandHandler("autoreply", autoreply, filters=new_message))
        app.add_handler(CommandHandler("exempt", exempt, filters=new_message))
        
        app.add_handler(MessageHandler(
            filters.UpdateType.MESSAGE & admin_chat & configured_admin &
            relayable_content,
            handle_admin_reply
        ))

        app.add_handler(MessageHandler(
            filters.UpdateType.EDITED_MESSAGE & admin_chat & configured_admin &
            relayable_content,
            handle_admin_edit
        ))
        
        app.add_handler(MessageHandler(
            filters.UpdateType.MESSAGE & relayable_content &
            filters.ChatType.PRIVATE,
            handle_message
        ))

        app.add_handler(MessageHandler(
            filters.UpdateType.EDITED_MESSAGE & relayable_content &
            filters.ChatType.PRIVATE,
            handle_edited_message
        ))
        
        app.add_handler(CallbackQueryHandler(handle_callback))
    else:
        print("警告: FORUM_GROUP_ID 或 ADMIN_IDS 未设置。已禁用大部分功能。")
