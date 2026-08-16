import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Optional

from telegram import ReplyParameters, Update
from telegram.ext import ContextTypes

from config import config


logger = logging.getLogger(__name__)

_BUFFER_KEY = "message_relay_media_groups"
_SEMAPHORE_KEY = "message_relay_worker_semaphore"
_SETTLE_SECONDS = 1.0
_MAX_ENTRIES_PER_CONVERSATION = max(20, config.MAX_MESSAGES_PER_MINUTE * 2)
_MAX_GLOBAL_ENTRIES = max(100, config.MAX_WORKERS * config.MAX_MESSAGES_PER_MINUTE * 4)


def _get_queue(context, conversation_id: int):
    queues = context.bot_data.setdefault(_BUFFER_KEY, {})
    queue = queues.get(conversation_id)
    if queue is None:
        queue = {
            "entries": [],
            "groups": {},
            "task": None,
        }
        queues[conversation_id] = queue
    return queues, queue


def _start_worker(context, queues, conversation_id: int, queue) -> None:
    task = queue.get("task")
    if task is not None and not task.done():
        return

    queue["task"] = context.application.create_task(
        _drain_queue(queues, conversation_id, queue),
        name=f"message-relay-{conversation_id}",
    )


def _worker_semaphore(context):
    semaphore = context.bot_data.get(_SEMAPHORE_KEY)
    if semaphore is None:
        semaphore = asyncio.Semaphore(max(1, config.MAX_WORKERS))
        context.bot_data[_SEMAPHORE_KEY] = semaphore
    return semaphore


def _queue_has_capacity(queues, queue) -> bool:
    global_entries = sum(
        len(existing_queue["entries"])
        for existing_queue in queues.values()
    )
    return (
        len(queue["entries"]) < _MAX_ENTRIES_PER_CONVERSATION
        and global_entries < _MAX_GLOBAL_ENTRIES
    )


def has_active_queue(
    context: ContextTypes.DEFAULT_TYPE,
    conversation_id: int,
) -> bool:
    queue = getattr(context, "bot_data", {}).get(_BUFFER_KEY, {}).get(conversation_id)
    return bool(queue and queue["entries"])


async def enqueue_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    scope: str,
    callback: Callable[
        [list[Update], ContextTypes.DEFAULT_TYPE],
        Awaitable[None],
    ],
    conversation_id: Optional[int] = None,
) -> bool:
    message = update.effective_message
    if not message:
        raise ValueError("enqueue_message 只能接收消息更新")

    conversation_id = conversation_id if conversation_id is not None else message.chat_id
    queues, queue = _get_queue(context, conversation_id)

    is_media_group = bool(update.message and message.media_group_id)
    group_key = None
    entry = None
    if is_media_group:
        group_key = (scope, message.chat_id, message.media_group_id)
        entry = queue["groups"].get(group_key)
        if entry is not None and entry["processing"]:
            entry = None

    if entry is None:
        if not _queue_has_capacity(queues, queue):
            if not queue["entries"] and queues.get(conversation_id) is queue:
                queues.pop(conversation_id, None)
            return False

        entry = {
            "updates": {},
            "generation": 0,
            "is_media_group": is_media_group,
            "group_key": group_key,
            "callback": callback,
            "context": context,
            "processing": False,
            "future": None,
            "is_job": False,
        }
        queue["entries"].append(entry)
        if group_key is not None:
            queue["groups"][group_key] = entry

    entry["updates"][message.message_id] = update
    entry["generation"] += 1
    entry["context"] = context
    _start_worker(context, queues, conversation_id, queue)
    return True


async def collect_media_group(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    scope: str,
    callback: Callable[
        [list[Update], ContextTypes.DEFAULT_TYPE],
        Awaitable[None],
    ],
) -> None:
    message = update.effective_message
    if not message or not message.media_group_id:
        raise ValueError("collect_media_group 只能接收相册消息")
    accepted = await enqueue_message(update, context, scope, callback)
    if not accepted:
        raise RuntimeError("消息队列已满")


def replace_buffered_update(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    scope: str,
    conversation_id: Optional[int] = None,
) -> bool:
    message = update.effective_message
    if not message:
        return False

    conversation_id = conversation_id if conversation_id is not None else message.chat_id
    queues = context.bot_data.get(_BUFFER_KEY, {})
    queue = queues.get(conversation_id)
    if not queue:
        return False

    for entry in queue["entries"]:
        if entry["processing"]:
            continue
        for buffered_update in entry["updates"].values():
            buffered_message = buffered_update.effective_message
            if (
                buffered_message
                and buffered_message.chat_id == message.chat_id
                and buffered_message.message_id == message.message_id
            ):
                entry["updates"][message.message_id] = update
                if entry["is_media_group"]:
                    entry["generation"] += 1
                return True
    return False


async def run_serialized(
    context: ContextTypes.DEFAULT_TYPE,
    conversation_id: int,
    callback: Callable[[], Awaitable[object]],
):
    future = enqueue_serialized(context, conversation_id, callback, wait=True)
    return await future


def enqueue_serialized(
    context: ContextTypes.DEFAULT_TYPE,
    conversation_id: int,
    callback: Callable[[], Awaitable[object]],
    *,
    wait: bool = False,
):
    queues, queue = _get_queue(context, conversation_id)
    if not _queue_has_capacity(queues, queue):
        if not queue["entries"] and queues.get(conversation_id) is queue:
            queues.pop(conversation_id, None)
        if wait:
            raise RuntimeError("消息队列已满")
        return False

    future = asyncio.get_running_loop().create_future() if wait else None
    queue["entries"].append({
        "updates": {},
        "generation": 0,
        "is_media_group": False,
        "group_key": None,
        "callback": callback,
        "context": context,
        "processing": False,
        "future": future,
        "is_job": True,
    })
    _start_worker(context, queues, conversation_id, queue)
    return future if wait else True


async def _wait_for_album(entry) -> None:
    while True:
        generation = entry["generation"]
        await asyncio.sleep(_SETTLE_SECONDS)
        if generation == entry["generation"]:
            return


async def _notify_message_failure(entry, error: Exception) -> None:
    if not entry["updates"]:
        return
    first_update = entry["updates"][min(entry["updates"])]
    message = first_update.effective_message
    if not message:
        return
    try:
        await entry["context"].bot.send_message(
            chat_id=message.chat_id,
            message_thread_id=(
                message.message_thread_id if message.is_topic_message else None
            ),
            text="这条消息未能完成传递，请稍后重新发送。",
            reply_parameters=ReplyParameters(
                message_id=message.message_id,
                allow_sending_without_reply=True,
            ),
        )
    except Exception as notification_error:
        logger.warning(
            "消息处理失败后无法通知发送方 (%s): %s",
            error,
            notification_error,
        )


async def _drain_queue(queues, conversation_id: int, queue) -> None:
    try:
        while queue["entries"]:
            entry = queue["entries"][0]
            if entry["is_media_group"]:
                await _wait_for_album(entry)

            entry["processing"] = True
            future = entry["future"]
            try:
                async with _worker_semaphore(entry["context"]):
                    if entry["is_job"]:
                        result = await entry["callback"]()
                    else:
                        updates = [
                            entry["updates"][message_id]
                            for message_id in sorted(entry["updates"])
                        ]
                        result = await entry["callback"](
                            updates,
                            entry["context"],
                        )
                if future is not None and not future.done():
                    future.set_result(result)
            except asyncio.CancelledError:
                if future is not None and not future.done():
                    future.cancel()
                raise
            except Exception as error:
                if future is not None and not future.done():
                    future.set_exception(error)
                else:
                    logger.exception("串行处理消息失败: %s", conversation_id)
                    await _notify_message_failure(entry, error)
            finally:
                queue["entries"].pop(0)
                group_key = entry["group_key"]
                if group_key is not None and queue["groups"].get(group_key) is entry:
                    queue["groups"].pop(group_key, None)
    finally:
        for pending_entry in queue["entries"]:
            future = pending_entry["future"]
            if future is not None and not future.done():
                future.cancel()
        if queues.get(conversation_id) is queue:
            queues.pop(conversation_id, None)
