import json
import os
import logging
from typing import Dict, Optional, Any
import feedparser

logger = logging.getLogger(__name__)

subscriptions_data: Dict[str, Dict[str, Any]] = {}


def get_feed_title(feed_url: str) -> Optional[str]:
    try:
        feed = feedparser.parse(feed_url)
        if feed.feed and feed.feed.title:
            return feed.feed.title
        logger.warning("无法获取订阅源的标题: %s", feed_url)
    except Exception as exc:
        logger.error("获取订阅源 %s 标题时出错: %s", feed_url, exc)
    return None


def _ensure_feed_data_structure(feed_data: Dict[str, Any], feed_url: str) -> None:
    if "keywords" not in feed_data:
        feed_data["keywords"] = []
    if "last_entry_id" not in feed_data:
        feed_data["last_entry_id"] = None
    if "title" not in feed_data:
        feed_data["title"] = get_feed_title(feed_url) or "未知标题"


def _ensure_user_data_structure(user_config: Dict[str, Any]) -> Dict[str, Any]:
    if "rss_feeds" not in user_config:
        user_config["rss_feeds"] = {}
    else:
        for feed_url, feed_data in user_config["rss_feeds"].items():
            _ensure_feed_data_structure(feed_data, feed_url)

    user_config.setdefault("custom_footer", None)
    user_config.setdefault("link_preview_enabled", True)
    return user_config


def load_subscriptions(data_file: str) -> Dict[str, Dict[str, Any]]:
    global subscriptions_data

    if not os.path.exists(data_file):
        logger.info("未找到 %s。初始化为空订阅。", data_file)
        subscriptions_data = {}
        return subscriptions_data

    try:
        with open(data_file, "r", encoding="utf-8") as file:
            loaded_data = json.load(file)

        subscriptions_data = {}
        for chat_id_str, user_config in loaded_data.items():
            chat_id = str(chat_id_str)
            subscriptions_data[chat_id] = _ensure_user_data_structure(user_config.copy())

        logger.info("订阅已成功从 %s 加载", data_file)
    except json.JSONDecodeError as exc:
        logger.error("解码 %s 出错: %s。初始化为空订阅。", data_file, exc)
        subscriptions_data = {}
    except Exception as exc:
        logger.error("从 %s 加载订阅出错: %s。初始化为空订阅。", data_file, exc)
        subscriptions_data = {}

    return subscriptions_data


def save_subscriptions(data_file: str) -> None:
    global subscriptions_data

    try:
        data_dir = os.path.dirname(data_file)
        if data_dir:
            os.makedirs(data_dir, exist_ok=True)

        with open(data_file, "w", encoding="utf-8") as file:
            json.dump(subscriptions_data, file, indent=4, ensure_ascii=False)
        logger.debug("订阅已成功保存到 %s", data_file)
    except Exception as exc:
        logger.error("保存订阅到 %s 时出错: %s", data_file, exc)


def get_subscriptions() -> Dict[str, Dict[str, Any]]:
    return subscriptions_data


def remove_feed(chat_id: str, feed_url: str, data_file: str) -> bool:
    if chat_id not in subscriptions_data:
        return False

    feeds = subscriptions_data[chat_id].get("rss_feeds", {})
    if feed_url not in feeds:
        return False

    del feeds[feed_url]
    if not feeds:
        subscriptions_data.pop(chat_id, None)

    save_subscriptions(data_file)
    return True


def remove_keyword(chat_id: str, feed_url: str, keyword: str, data_file: str) -> bool:
    if chat_id not in subscriptions_data:
        return False

    feed_data = subscriptions_data[chat_id].get("rss_feeds", {}).get(feed_url)
    if not feed_data:
        return False

    keywords = feed_data.get("keywords", [])
    lowered = keyword.lower()
    for existing in keywords:
        if existing.lower() == lowered:
            keywords.remove(existing)
            save_subscriptions(data_file)
            return True
    return False

