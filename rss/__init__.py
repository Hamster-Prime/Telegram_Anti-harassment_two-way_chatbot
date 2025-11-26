import logging
import os
from telegram.ext import Application, CommandHandler, filters
from telegram.ext import Job
from typing import Optional
from . import data_manager, feed_checker, handlers as rss_handlers, settings

logger = logging.getLogger(__name__)

RSS_JOB_KEY = "rss_feed_job"


def _schedule_feed_job(app: Application) -> Optional[Job]:
    interval = settings.get_check_interval()
    if not isinstance(interval, int) or interval <= 0:
        logger.warning("RSS 检查间隔无效 (%s)，回退为 300 秒。", interval)
        interval = 300

    job = app.job_queue.run_repeating(
        feed_checker.check_feeds_job,
        interval=interval,
        first=10,
        name="rss_feed_checker",
    )
    app.bot_data[RSS_JOB_KEY] = job
    logger.info("RSS 订阅检查任务已调度，间隔 %s 秒", interval)
    return job


def _cancel_feed_job(app: Application) -> None:
    job = app.bot_data.pop(RSS_JOB_KEY, None)
    if job:
        job.schedule_removal()
        logger.info("RSS 订阅检查任务已停止。")


def setup(app: Application) -> None:
    data_file = settings.get_data_file() or "./data/rss_subscriptions.json"
    data_dir = os.path.dirname(data_file)
    if data_dir:
        os.makedirs(data_dir, exist_ok=True)

    data_manager.load_subscriptions(data_file)
    app.bot_data["rss_data_file"] = data_file

    for command, handler in rss_handlers.COMMAND_MAP.items():
        app.add_handler(CommandHandler(command, handler, filters=filters.ChatType.PRIVATE))

    if settings.is_enabled():
        _schedule_feed_job(app)
        logger.info("RSS 订阅功能已启用，数据文件: %s", data_file)
    else:
        logger.info("RSS 订阅功能当前为关闭状态，可在面板中开启。")


def enable_feature(app: Application) -> bool:
    if settings.is_enabled():
        return False
    settings.set_enabled(True)
    _schedule_feed_job(app)
    logger.info("RSS 订阅功能已在运行时开启。")
    return True


def disable_feature(app: Application) -> bool:
    if not settings.is_enabled():
        return False
    settings.set_enabled(False)
    _cancel_feed_job(app)
    logger.info("RSS 订阅功能已在运行时关闭。")
    return True

