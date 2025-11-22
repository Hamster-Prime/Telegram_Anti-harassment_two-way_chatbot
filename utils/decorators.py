from functools import wraps
from telegram import Update
from telegram.ext import ContextTypes
from database.models import is_admin
from config import config

def admin_only(func):
    @wraps(func)
    async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user = update.effective_user
        if not config.ADMIN_IDS:
            await update.message.reply_text("抱歉，管理员功能尚未启用。")
            return
        if not await is_admin(user.id):
            await update.message.reply_text("抱歉，此功能仅限管理员使用。")
            return
        return await func(update, context, *args, **kwargs)
    return wrapped
