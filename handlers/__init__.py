from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters
from .command_handler import start, help_command, block, unblock, blacklist, stats, getid, autoreply, panel
from .user_handler import handle_message
from .callback_handler import handle_callback
from .admin_handler import handle_admin_reply, view_filtered
from config import config

def register_handlers(app: Application):
    app.add_handler(CommandHandler("getid", getid))
    app.add_handler(CommandHandler("start", start, filters=filters.ChatType.PRIVATE))

    if config.FORUM_GROUP_ID and config.ADMIN_IDS:
        app.add_handler(CommandHandler("help", help_command, filters=filters.ChatType.PRIVATE))
        app.add_handler(CommandHandler("block", block))
        app.add_handler(CommandHandler("unblock", unblock))
        app.add_handler(CommandHandler("panel", panel))
        app.add_handler(CommandHandler("blacklist", blacklist))
        app.add_handler(CommandHandler("stats", stats))
        app.add_handler(CommandHandler("view_filtered", view_filtered))
        app.add_handler(CommandHandler("autoreply", autoreply))
        
        app.add_handler(MessageHandler(
            filters.Chat(chat_id=config.FORUM_GROUP_ID) & filters.REPLY & ~filters.COMMAND,
            handle_admin_reply
        ))
        
        app.add_handler(MessageHandler(
            (filters.TEXT | filters.PHOTO | filters.VIDEO | filters.AUDIO | filters.VOICE |
             filters.Document.ALL | filters.Sticker.ALL | filters.ANIMATION) &
            ~filters.COMMAND & filters.ChatType.PRIVATE,
            handle_message
        ))
        
        app.add_handler(CallbackQueryHandler(handle_callback))
    else:
        print("警告: FORUM_GROUP_ID 或 ADMIN_IDS 未设置。已禁用大部分功能。")
