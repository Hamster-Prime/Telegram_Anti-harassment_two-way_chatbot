from telegram import Update
from telegram.ext import ContextTypes
from config import config

async def send_message_by_type(bot, message, chat_id, thread_id=None, disable_web_page_preview=False):
    if message.text:
        return await bot.send_message(
            chat_id=chat_id,
            text=message.text,
            entities=message.entities,
            message_thread_id=thread_id,
            disable_web_page_preview=disable_web_page_preview
        )
    elif message.photo:
        return await bot.send_photo(
            chat_id=chat_id,
            photo=message.photo[-1].file_id,
            caption=message.caption,
            caption_entities=message.caption_entities,
            message_thread_id=thread_id
        )
    elif message.animation:
        return await bot.send_animation(
            chat_id=chat_id,
            animation=message.animation.file_id,
            caption=message.caption,
            caption_entities=message.caption_entities,
            message_thread_id=thread_id
        )
    elif message.video:
        return await bot.send_video(
            chat_id=chat_id,
            video=message.video.file_id,
            caption=message.caption,
            caption_entities=message.caption_entities,
            message_thread_id=thread_id
        )
    elif message.document:
        return await bot.send_document(
            chat_id=chat_id,
            document=message.document.file_id,
            caption=message.caption,
            caption_entities=message.caption_entities,
            message_thread_id=thread_id
        )
    elif message.audio:
        return await bot.send_audio(
            chat_id=chat_id,
            audio=message.audio.file_id,
            caption=message.caption,
            caption_entities=message.caption_entities,
            message_thread_id=thread_id
        )
    elif message.voice:
        return await bot.send_voice(
            chat_id=chat_id,
            voice=message.voice.file_id,
            caption=message.caption,
            caption_entities=message.caption_entities,
            message_thread_id=thread_id
        )
    elif message.video_note:
        return await bot.send_video_note(
            chat_id=chat_id,
            video_note=message.video_note.file_id,
            message_thread_id=thread_id
        )
    elif message.sticker:
        return await bot.send_sticker(
            chat_id=chat_id,
            sticker=message.sticker.file_id,
            message_thread_id=thread_id
        )
    return None

