import asyncio
import logging
import feedparser
from typing import Dict, Any, Optional
from telegram.ext import ContextTypes
from telegram import constants
from config import config
from . import data_manager, retry_utils, settings

logger = logging.getLogger(__name__)


async def send_telegram_message(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: str,
    text: str,
) -> None:
    try:
        subscriptions_data = data_manager.get_subscriptions()
        user_chat_id_str = str(chat_id)
        user_data = subscriptions_data.get(user_chat_id_str, {})
        custom_footer = user_data.get("custom_footer")
        link_preview_enabled = user_data.get("link_preview_enabled", True)

        if custom_footer:
            text += f"\n---\n{custom_footer}"

        await retry_utils.retry_telegram_api(
            context.bot.send_message,
            chat_id=chat_id,
            text=text,
            parse_mode=constants.ParseMode.HTML,
            disable_web_page_preview=not link_preview_enabled,
        )
    except Exception as exc:
        logger.error("向 %s 发送消息时出错: %s", chat_id, exc)


def _get_entry_id(entry: Dict[str, Any]) -> Optional[str]:
    return entry.get("id") or entry.get("link")


def _matches_keywords(entry: Dict[str, Any], keywords: list) -> bool:
    if not keywords:
        return True

    title = entry.get("title", "")
    summary = entry.get("summary", "")
    content_to_check = f"{title} {summary}".lower()

    return any(keyword.lower() in content_to_check for keyword in keywords)


def _update_last_entry_id(
    chat_id: str,
    feed_url: str,
    entry_id: str,
    data_file: str,
) -> None:
    subscriptions_data = data_manager.get_subscriptions()
    if chat_id in subscriptions_data and feed_url in subscriptions_data[chat_id].get("rss_feeds", {}):
        subscriptions_data[chat_id]["rss_feeds"][feed_url]["last_entry_id"] = entry_id
        data_manager.save_subscriptions(data_file)


async def check_single_feed(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: str,
    feed_url: str,
    feed_config: Dict[str, Any],
    data_file: str,
) -> None:
    logger.info("正在为用户 %s 检查订阅源: %s", chat_id, feed_url)

    try:
        if hasattr(asyncio, "to_thread"):
            feed_content = await asyncio.to_thread(feedparser.parse, feed_url)
        else:
            loop = asyncio.get_event_loop()
            feed_content = await loop.run_in_executor(None, feedparser.parse, feed_url)

        if feed_content.bozo:
            logger.warning(
                "用户 %s 的订阅源 %s 可能格式错误。Bozo 标记: %s",
                chat_id,
                feed_url,
                feed_content.bozo_exception,
            )

        last_known_entry_id = feed_config.get("last_entry_id")
        current_feed_latest_entry_id = None

        if feed_content.entries:
            latest_entry = feed_content.entries[0]
            current_feed_latest_entry_id = _get_entry_id(latest_entry)

        if last_known_entry_id is None:
            if current_feed_latest_entry_id:
                _update_last_entry_id(chat_id, feed_url, current_feed_latest_entry_id, data_file)
                logger.info(
                    "首次检查 %s (用户 %s)。将 last_entry_id 设置为 %s。此周期不发送初始帖子。",
                    feed_url,
                    chat_id,
                    current_feed_latest_entry_id,
                )
            return

        temp_new_entries = []
        found_last_known = False

        for entry in feed_content.entries:
            entry_id = _get_entry_id(entry)
            if not entry_id:
                logger.warning("%s 中的条目缺少 'id' 和 'link'。正在跳过。", feed_url)
                continue

            if last_known_entry_id == entry_id:
                found_last_known = True
                break
            temp_new_entries.append(entry)

        if not found_last_known and last_known_entry_id is not None:
            logger.warning(
                "在用户 %s 的 %s 当前获取中未找到最后已知条目 ID '%s'。"
                "如果存在，则最多发送 5 个最新项目。",
                chat_id,
                feed_url,
                last_known_entry_id,
            )
            new_entries = list(reversed(temp_new_entries[:5]))
        else:
            new_entries = list(reversed(temp_new_entries))

        sent_count = 0
        latest_sent_entry_id_this_cycle = None
        keywords = feed_config.get("keywords", [])
        feed_title = feed_config.get("title", feed_url)

        for entry in new_entries:
            if not _matches_keywords(entry, keywords):
                title = entry.get("title", "无标题")
                logger.debug(
                    "来自 %s 的条目 '%s' 因用户 %s 的关键词不匹配而被跳过。",
                    feed_url,
                    title,
                    chat_id,
                )
                continue

            entry_id = _get_entry_id(entry)
            title = entry.get("title", "无标题")
            link = entry.get("link", "")
            message = f"<b>{feed_title}</b>\n<a href='{link}'>{title}</a>"

            await send_telegram_message(context, chat_id, message)
            sent_count += 1
            latest_sent_entry_id_this_cycle = entry_id

            if sent_count >= 5 and len(new_entries) > 7:
                remaining = len(new_entries) - sent_count
                await send_telegram_message(
                    context,
                    chat_id,
                    f"<i>...以及来自 {feed_title} 的 {remaining} 个更多新条目。</i>",
                )
                logger.info(
                    "已向用户 %s 发送 %s 个来自 %s 的条目，还有更多可用。",
                    chat_id,
                    sent_count,
                    feed_url,
                )
                break

        if latest_sent_entry_id_this_cycle:
            _update_last_entry_id(chat_id, feed_url, latest_sent_entry_id_this_cycle, data_file)
            logger.info(
                "已向用户 %s 发送 %s 个来自 %s 的新条目。已将 last_entry_id 更新为 %s。",
                chat_id,
                sent_count,
                feed_url,
                latest_sent_entry_id_this_cycle,
            )
        elif not new_entries and current_feed_latest_entry_id:
            subscriptions_data = data_manager.get_subscriptions()
            current_last_id = (
                subscriptions_data.get(chat_id, {})
                .get("rss_feeds", {})
                .get(feed_url, {})
                .get("last_entry_id")
            )
            if current_last_id != current_feed_latest_entry_id:
                _update_last_entry_id(chat_id, feed_url, current_feed_latest_entry_id, data_file)
                logger.info(
                    "未向用户 %s 发送来自 %s 的新条目 (例如已过滤)。"
                    "已将 last_entry_id 更新为订阅源中的最新条目: %s。",
                    chat_id,
                    feed_url,
                    current_feed_latest_entry_id,
                )
        elif sent_count == 0 and new_entries:
            id_of_newest_identified_entry = _get_entry_id(new_entries[-1])
            if id_of_newest_identified_entry:
                _update_last_entry_id(chat_id, feed_url, id_of_newest_identified_entry, data_file)
                logger.info(
                    "用户 %s 的 %s 中的所有新条目均已过滤。已将 last_entry_id 更新为 %s。",
                    chat_id,
                    feed_url,
                    id_of_newest_identified_entry,
                )

    except Exception as exc:
        logger.error("处理用户 %s 的订阅源 %s 时出错: %s", chat_id, feed_url, exc, exc_info=True)


async def check_feeds_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    if not settings.is_enabled():
        logger.debug("RSS 功能已关闭，跳过本次检查任务。")
        return

    data_file = context.application.bot_data.get("rss_data_file", config.RSS_DATA_FILE)
    if not data_file:
        logger.warning("未配置 RSS 数据文件，跳过此次检查。")
        return

    logger.info("正在运行定期订阅源检查...")
    subscriptions_data = data_manager.get_subscriptions()

    if not subscriptions_data:
        logger.info("没有要检查的订阅。")
        return

    all_feed_checks = []
    for chat_id, user_data in list(subscriptions_data.items()):
        feeds = user_data.get("rss_feeds", {})
        for feed_url, feed_config in list(feeds.items()):
            all_feed_checks.append(
                check_single_feed(context, chat_id, feed_url, dict(feed_config), data_file)
            )

    if not all_feed_checks:
        logger.info("在 subscriptions_data 中未找到要检查的订阅源。")
        return

    logger.info("已计划 %s 个订阅源检查，将并发执行。", len(all_feed_checks))
    results = await asyncio.gather(*all_feed_checks, return_exceptions=True)

    error_count = 0
    for idx, result in enumerate(results):
        if isinstance(result, Exception):
            error_count += 1
            logger.error("订阅源检查任务 %s 失败: %s", idx, result)

    if error_count > 0:
        logger.warning("此周期有 %s/%s 个订阅源检查失败。", error_count, len(all_feed_checks))
    else:
        logger.info("此周期的所有订阅源检查已完成。")

