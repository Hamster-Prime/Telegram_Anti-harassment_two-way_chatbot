from datetime import datetime

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes
from telegram.helpers import escape_markdown

from config import config
from database import models as db


def build_direct_contact_url(username: str | None) -> str | None:
    if not username:
        return None
    return f"tg://resolve?domain={username}"


def build_user_info_markdown(user) -> str:
    name_parts = [part.strip() for part in [user.first_name or "", user.last_name or ""] if part and part.strip()]
    display_name = " ".join(name_parts) if name_parts else str(user.id)
    username = f"@{user.username}" if user.username else "未设置"
    first_contact = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    escaped_display_name = escape_markdown(display_name, version=2)
    escaped_username = escape_markdown(username, version=2)
    escaped_first_contact = escape_markdown(first_contact, version=2)

    return (
        "*用户信息*\n\n"
        f"*名称:* {escaped_display_name}\n"
        f"*TG ID:* `{user.id}`\n"
        f"*用户名:* {escaped_username}\n"
        f"*首次联系:* {escaped_first_contact}"
    )


async def get_or_create_thread(update: Update, context: ContextTypes.DEFAULT_TYPE) -> tuple[int, bool]:
    user = update.effective_user
    user_data = await db.get_user(user.id)

    if user_data and user_data.get('thread_id'):
        return user_data['thread_id'], False

    topic_name = f"{user.first_name} (ID: {user.id})"
    try:
        topic = await context.bot.create_forum_topic(
            chat_id=config.FORUM_GROUP_ID,
            name=topic_name
        )
        thread_id = topic.message_thread_id

        await db.update_user_thread_id(user.id, thread_id)

        try:
            await send_user_info_card(update, context, thread_id)
        except Exception as e:
            print(f"发送用户信息卡片失败: {e}")

        from handlers.user_handler import _resend_message
        await _resend_message(update, context, thread_id)

        return thread_id, True
    except Exception as e:
        print(f"创建话题失败: {e}")
        return None, False


async def build_user_info_card_keyboard(
    user_id: int,
    username: str | None = None
) -> InlineKeyboardMarkup:
    is_blocked, _ = await db.is_blacklisted(user_id)
    is_exempted = await db.is_exempted(user_id)

    if username is None:
        user_data = await db.get_user(user_id)
        username = user_data.get("username") if user_data else None

    row = [
        InlineKeyboardButton(
            "解除封禁" if is_blocked else "封禁",
            callback_data=f"usercard_block_{user_id}"
        ),
        InlineKeyboardButton(
            "取消豁免" if is_exempted else "豁免",
            callback_data=f"usercard_exempt_{user_id}"
        ),
    ]

    direct_contact_url = build_direct_contact_url(username)
    if direct_contact_url:
        row.append(InlineKeyboardButton("直接联系", url=direct_contact_url))

    return InlineKeyboardMarkup([row])


async def send_user_info_card(update: Update, context: ContextTypes.DEFAULT_TYPE, thread_id: int):
    user = update.effective_user
    reply_markup = await build_user_info_card_keyboard(user.id, username=user.username)
    info_text = build_user_info_markdown(user)

    photos = None
    try:
        photos = await context.bot.get_user_profile_photos(user.id, limit=1)
    except Exception as e:
        print(f"获取用户头像失败: {e}")

    if photos and photos.total_count > 0:
        try:
            await context.bot.send_photo(
                chat_id=config.FORUM_GROUP_ID,
                photo=photos.photos[0][0].file_id,
                caption=info_text,
                message_thread_id=thread_id,
                parse_mode=ParseMode.MARKDOWN_V2,
                reply_markup=reply_markup
            )
            return
        except Exception as e:
            print(f"发送头像卡片失败，改用文本卡片: {e}")

    await context.bot.send_message(
        chat_id=config.FORUM_GROUP_ID,
        text=info_text,
        message_thread_id=thread_id,
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=reply_markup
    )
