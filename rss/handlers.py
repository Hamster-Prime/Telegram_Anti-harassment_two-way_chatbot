import logging
import asyncio
from urllib.parse import urlparse
from typing import Optional, Dict, Any
from telegram import Update
from telegram.ext import ContextTypes
from config import config
from . import data_manager, settings as rss_settings
from .auth import is_authorized

logger = logging.getLogger(__name__)


def _get_message(update: Update):
    return update.effective_message


def _get_data_file(context: ContextTypes.DEFAULT_TYPE) -> str:
    if context and context.application:
        return context.application.bot_data.get("rss_data_file", config.RSS_DATA_FILE)
    return config.RSS_DATA_FILE


async def _ensure_access(update: Update):
    message = _get_message(update)
    if not message:
        return None

    user = update.effective_user
    user_id = user.id if user else None

    if not is_authorized(user_id):
        await message.reply_text("抱歉，RSS 功能仅向管理员或被授权用户开放。")
        return None

    if not rss_settings.is_enabled():
        await message.reply_text("RSS 功能当前已关闭，请联系管理员在 /panel → RSS 功能管理 中开启。")
        return None

    return message


def is_valid_url(url_string: str) -> bool:
    try:
        result = urlparse(url_string)
        return all([result.scheme, result.netloc])
    except ValueError:
        return False


def get_chat_id(update: Update) -> str:
    chat = update.effective_chat
    return str(chat.id) if chat else ""


def ensure_user_data(chat_id: str, subscriptions_data: Dict[str, Any]) -> None:
    if chat_id not in subscriptions_data:
        subscriptions_data[chat_id] = {
            "rss_feeds": {},
            "custom_footer": None,
            "link_preview_enabled": True,
        }
    else:
        subscriptions_data[chat_id].setdefault("rss_feeds", {})
        subscriptions_data[chat_id].setdefault("custom_footer", None)
        subscriptions_data[chat_id].setdefault("link_preview_enabled", True)


def find_feed_by_identifier(
    feed_identifier: str,
    feeds: Dict[str, Any],
) -> Optional[str]:
    if feed_identifier.isdigit():
        feed_index = int(feed_identifier) - 1
        feed_list = list(feeds.keys())
        if 0 <= feed_index < len(feed_list):
            return feed_list[feed_index]

    if feed_identifier in feeds:
        return feed_identifier

    return None


async def add_feed(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = await _ensure_access(update)
    if not message:
        return

    chat_id = get_chat_id(update)
    if not context.args:
        await message.reply_text("请输入 RSS 订阅源链接。用法: /rss_add <链接>")
        return

    feed_url = context.args[0]
    if not is_valid_url(feed_url):
        await message.reply_text(f"提供的链接 '{feed_url}' 似乎无效。请检查后重试。")
        return

    subscriptions_data = data_manager.get_subscriptions()
    ensure_user_data(chat_id, subscriptions_data)

    if feed_url in subscriptions_data[chat_id]["rss_feeds"]:
        await message.reply_text(f"订阅源 {feed_url} 已在您的订阅中。")
        return

    if hasattr(asyncio, "to_thread"):
        feed_title = await asyncio.to_thread(data_manager.get_feed_title, feed_url) or "未知标题"
    else:
        loop = asyncio.get_event_loop()
        feed_title = await loop.run_in_executor(None, data_manager.get_feed_title, feed_url) or "未知标题"

    subscriptions_data[chat_id]["rss_feeds"][feed_url] = {
        "title": feed_title,
        "keywords": [],
        "last_entry_id": None,
    }
    data_manager.save_subscriptions(_get_data_file(context))

    reply_message_text = f"订阅源 '{feed_title}' ({feed_url}) 添加成功！"
    await message.reply_text(reply_message_text)
    logger.info("用户 %s 添加了订阅源: %s", chat_id, feed_url)


async def list_feeds(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = await _ensure_access(update)
    if not message:
        return

    chat_id = get_chat_id(update)
    subscriptions_data = data_manager.get_subscriptions()

    feeds = subscriptions_data.get(chat_id, {}).get("rss_feeds", {})
    if not feeds:
        await message.reply_text("您还没有订阅任何 RSS 源。使用 /rss_add <链接> 添加一个。")
        return

    message_content = "您当前的 RSS 订阅:\n"
    for idx, (url, data) in enumerate(feeds.items(), 1):
        title = data.get("title", "N/A")
        keywords_list = data.get("keywords", [])
        keywords_str = f" (关键词: {', '.join(keywords_list)})" if keywords_list else ""
        message_content += f"{idx}. {title} - {url}{keywords_str}\n"

    await message.reply_text(message_content)


async def remove_feed(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = await _ensure_access(update)
    if not message:
        return

    chat_id = get_chat_id(update)

    if not context.args:
        await message.reply_text("请输入要移除的 RSS 订阅源链接或其 ID (来自 /rss_list)。用法: /rss_remove <链接或ID>")
        return

    identifier = context.args[0]
    subscriptions_data = data_manager.get_subscriptions()
    feeds = subscriptions_data.get(chat_id, {}).get("rss_feeds", {})

    if not feeds:
        await message.reply_text("您没有任何订阅可以移除。")
        return

    feed_to_remove = find_feed_by_identifier(identifier, feeds)

    if feed_to_remove:
        removed_title = feeds[feed_to_remove].get("title", feed_to_remove)
        del subscriptions_data[chat_id]["rss_feeds"][feed_to_remove]

        if not subscriptions_data[chat_id]["rss_feeds"]:
            del subscriptions_data[chat_id]

        data_manager.save_subscriptions(_get_data_file(context))
        reply_message_text = f"订阅源 '{removed_title}' 移除成功。"
        logger.info("用户 %s 移除了订阅源: %s", chat_id, feed_to_remove)
    else:
        reply_message_text = f"找不到标识符为 '{identifier}' 的订阅源。使用 /rss_list 查看您的订阅源及其 ID/链接。"

    await message.reply_text(reply_message_text)


async def add_keyword(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = await _ensure_access(update)
    if not message:
        return

    chat_id = get_chat_id(update)

    if len(context.args) < 2:
        await message.reply_text("用法: /rss_addkeyword <RSS链接或ID> <关键词>")
        return

    feed_identifier = context.args[0]
    keyword_to_add = " ".join(context.args[1:]).lower()
    subscriptions_data = data_manager.get_subscriptions()
    feeds = subscriptions_data.get(chat_id, {}).get("rss_feeds", {})

    if not feeds:
        await message.reply_text("您没有任何订阅可以添加关键词。")
        return

    target_feed_url = find_feed_by_identifier(feed_identifier, feeds)

    if not target_feed_url:
        await message.reply_text(f"找不到标识符为 '{feed_identifier}' 的订阅源。请使用 /rss_list 查看。")
        return

    feed_data = subscriptions_data[chat_id]["rss_feeds"][target_feed_url]
    feed_data.setdefault("keywords", [])

    if keyword_to_add in feed_data["keywords"]:
        feed_title = feed_data.get("title", target_feed_url)
        await message.reply_text(f"关键词 '{keyword_to_add}' 已存在于 '{feed_title}'。")
    else:
        feed_data["keywords"].append(keyword_to_add)
        data_manager.save_subscriptions(_get_data_file(context))
        feed_title = feed_data.get("title", target_feed_url)
        await message.reply_text(f"关键词 '{keyword_to_add}' 已添加到 '{feed_title}'。")
        logger.info("用户 %s 向订阅源 %s 添加了关键词 '%s'", chat_id, target_feed_url, keyword_to_add)


async def remove_keyword(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = await _ensure_access(update)
    if not message:
        return

    chat_id = get_chat_id(update)

    if len(context.args) < 2:
        await message.reply_text("用法: /rss_removekeyword <RSS链接或ID> <关键词>")
        return

    feed_identifier = context.args[0]
    keyword_to_remove = " ".join(context.args[1:]).lower()
    subscriptions_data = data_manager.get_subscriptions()
    feeds = subscriptions_data.get(chat_id, {}).get("rss_feeds", {})

    if not feeds:
        await message.reply_text("您没有任何订阅可以移除关键词。")
        return

    target_feed_url = find_feed_by_identifier(feed_identifier, feeds)

    if not target_feed_url:
        await message.reply_text(f"找不到标识符为 '{feed_identifier}' 的订阅源。请使用 /rss_list 查看。")
        return

    feed_data = subscriptions_data[chat_id]["rss_feeds"][target_feed_url]
    feed_title = feed_data.get("title", target_feed_url)

    if keyword_to_remove in feed_data.get("keywords", []):
        feed_data["keywords"].remove(keyword_to_remove)
        data_manager.save_subscriptions(_get_data_file(context))
        await message.reply_text(f"关键词 '{keyword_to_remove}' 已从 '{feed_title}' 移除。")
        logger.info("用户 %s 从订阅源 %s 移除了关键词 '%s'", chat_id, target_feed_url, keyword_to_remove)
    else:
        await message.reply_text(f"关键词 '{keyword_to_remove}' 未在 '{feed_title}' 中找到。")


async def list_keywords(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = await _ensure_access(update)
    if not message:
        return

    chat_id = get_chat_id(update)

    if not context.args:
        await message.reply_text("用法: /rss_listkeywords <RSS链接或ID>")
        return

    feed_identifier = context.args[0]
    subscriptions_data = data_manager.get_subscriptions()
    feeds = subscriptions_data.get(chat_id, {}).get("rss_feeds", {})

    if not feeds:
        await message.reply_text("您没有任何订阅。")
        return

    target_feed_url = find_feed_by_identifier(feed_identifier, feeds)

    if not target_feed_url:
        await message.reply_text(f"找不到标识符为 '{feed_identifier}' 的订阅源。请使用 /rss_list 查看。")
        return

    feed_data = subscriptions_data[chat_id]["rss_feeds"][target_feed_url]
    keywords = feed_data.get("keywords", [])
    title = feed_data.get("title", target_feed_url)

    if keywords:
        reply_message_text = f"'{title}' 的关键词:\n- " + "\n- ".join(keywords)
    else:
        reply_message_text = f"'{title}' 未设置关键词。将发送所有新项目。"

    await message.reply_text(reply_message_text)


async def remove_all_keywords(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = await _ensure_access(update)
    if not message:
        return

    chat_id = get_chat_id(update)

    if not context.args:
        await message.reply_text("用法: /rss_removeallkeywords <RSS链接或ID>")
        return

    feed_identifier = context.args[0]
    subscriptions_data = data_manager.get_subscriptions()
    feeds = subscriptions_data.get(chat_id, {}).get("rss_feeds", {})

    if not feeds:
        await message.reply_text("您没有任何订阅。")
        return

    target_feed_url = find_feed_by_identifier(feed_identifier, feeds)

    if not target_feed_url:
        await message.reply_text(f"找不到标识符为 '{feed_identifier}' 的订阅源。请使用 /rss_list 查看。")
        return

    feed_data = subscriptions_data[chat_id]["rss_feeds"][target_feed_url]
    feed_title = feed_data.get("title", target_feed_url)

    if feed_data.get("keywords"):
        feed_data["keywords"] = []
        data_manager.save_subscriptions(_get_data_file(context))
        await message.reply_text(f"已成功移除订阅源 '{feed_title}' 的所有关键词。")
        logger.info("用户 %s 移除了订阅源 %s 的所有关键词。", chat_id, target_feed_url)
    else:
        await message.reply_text(f"订阅源 '{feed_title}' 原本就没有设置关键词。")


async def set_custom_footer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = await _ensure_access(update)
    if not message:
        return

    chat_id = get_chat_id(update)
    subscriptions_data = data_manager.get_subscriptions()
    ensure_user_data(chat_id, subscriptions_data)

    footer_text = " ".join(context.args) if context.args else None
    subscriptions_data[chat_id]["custom_footer"] = footer_text
    data_manager.save_subscriptions(_get_data_file(context))

    if footer_text:
        reply_message_text = f"自定义页脚已设置为:\n{footer_text}"
    else:
        reply_message_text = "自定义页脚已清除。"

    logger.info("用户 %s 将自定义页脚设置为: '%s'", chat_id, footer_text)
    await message.reply_text(reply_message_text)


async def toggle_link_preview(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = await _ensure_access(update)
    if not message:
        return

    chat_id = get_chat_id(update)
    subscriptions_data = data_manager.get_subscriptions()
    ensure_user_data(chat_id, subscriptions_data)

    current_status = subscriptions_data[chat_id].get("link_preview_enabled", True)
    new_status = not current_status
    subscriptions_data[chat_id]["link_preview_enabled"] = new_status
    data_manager.save_subscriptions(_get_data_file(context))

    status_text = "开启" if new_status else "关闭"
    reply_message_text = f"链接预览已切换为: {status_text}。"

    logger.info("用户 %s 将链接预览切换为: %s", chat_id, status_text)
    await message.reply_text(reply_message_text)


async def add_authorized_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = _get_message(update)
    if not message:
        return

    user = update.effective_user
    if not user or user.id not in config.ADMIN_IDS:
        await message.reply_text("只有管理员可以添加 RSS 授权用户。")
        return

    if not context.args:
        await message.reply_text("用法: /rss_add_user <user_id>")
        return

    try:
        target_id = int(context.args[0])
    except ValueError:
        await message.reply_text("请输入有效的用户 ID（整数）。")
        return

    added = rss_settings.add_authorized_user(target_id)
    if added:
        await message.reply_text(f"已将用户 {target_id} 加入 RSS 授权列表。")
        logger.info("管理员 %s 添加了 RSS 授权用户 %s", user.id, target_id)
    else:
        await message.reply_text(f"用户 {target_id} 已在 RSS 授权列表中。")


async def remove_authorized_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = _get_message(update)
    if not message:
        return

    user = update.effective_user
    if not user or user.id not in config.ADMIN_IDS:
        await message.reply_text("只有管理员可以移除 RSS 授权用户。")
        return

    if not context.args:
        await message.reply_text("用法: /rss_rm_user <user_id>")
        return

    try:
        target_id = int(context.args[0])
    except ValueError:
        await message.reply_text("请输入有效的用户 ID（整数）。")
        return

    removed = rss_settings.remove_authorized_user(target_id)
    if removed:
        await message.reply_text(f"已将用户 {target_id} 从 RSS 授权列表移除。")
        logger.info("管理员 %s 移除了 RSS 授权用户 %s", user.id, target_id)
    else:
        await message.reply_text(f"用户 {target_id} 不在 RSS 授权列表中。")


COMMAND_MAP = {
    "rss_add": add_feed,
    "rss_remove": remove_feed,
    "rss_list": list_feeds,
    "rss_addkeyword": add_keyword,
    "rss_removekeyword": remove_keyword,
    "rss_listkeywords": list_keywords,
    "rss_removeallkeywords": remove_all_keywords,
    "rss_setfooter": set_custom_footer,
    "rss_togglepreview": toggle_link_preview,
    "rss_add_user": add_authorized_user,
    "rss_rm_user": remove_authorized_user,
}

