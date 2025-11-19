from telegram import Update
from telegram.ext import ContextTypes
from database import models as db
from services.blacklist import block_user, unblock_user, get_blacklist_keyboard 
from utils.decorators import admin_only

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    
    if not await db.get_user(user.id):
        await db.add_user(
            user_id=user.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name,
            language_code=user.language_code
        )
    
    welcome_message = (
        f"你好, {user.first_name}!\n\n"
        "欢迎使用双向聊天机器人。\n"
        "你可以直接在这里发送消息，管理员会尽快回复你。\n\n"
        "输入 /help 查看更多帮助信息。"
    )
    
    await update.message.reply_text(welcome_message)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "这是一个双向聊天机器人。\n\n"
        "功能列表:\n"
        "- 发送文本、图片、视频、音频和文档\n"
        "- 支持Markdown格式\n"
        "- 首次发送消息需要进行人机验证\n\n"
        "管理员命令:\n"
        "- `/block` - 在用户话题输入拉黑用户\n"
        "- `/blacklist` - 查看黑名单\n"
        "- `/stats` - 查看统计信息\n"
    )
    
    await update.message.reply_text(help_text, parse_mode='Markdown')

from services.blacklist import block_user, unblock_user, get_blacklist_keyboard
from utils.decorators import admin_only

@admin_only
async def blacklist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message, keyboard = await get_blacklist_keyboard(page=1)
    if keyboard:
        await update.message.reply_text(message, reply_markup=keyboard, parse_mode='Markdown')
    else:
        await update.message.reply_text(message)

@admin_only
async def block(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    
    
    if message.is_topic_message and message.reply_to_message:
        thread_id = message.message_thread_id
        user_to_block = await db.get_user_by_thread_id(thread_id)
        
        if user_to_block:
            user_id_to_block = user_to_block['user_id']
            reason = " ".join(context.args) if context.args else "无"
            
            response = await block_user(user_id_to_block, reason, update.effective_user.id, permanent=True)
            await update.message.reply_text(response)
        else:
            await update.message.reply_text("无法找到该话题对应的用户。")
        return

    
    if not context.args:
        await update.message.reply_text("请提供用户ID或在话题中回复。用法: /block <user_id> [reason]")
        return
    
    try:
        user_id_to_block = int(context.args[0])
        reason = " ".join(context.args[1:]) if len(context.args) > 1 else "无"
        response = await block_user(user_id_to_block, reason, update.effective_user.id)
        await update.message.reply_text(response)
    except (ValueError, IndexError):
        await update.message.reply_text("无效的用户ID。")

@admin_only
async def unblock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("请提供用户ID。用法: /unblock <user_id>")
        return
    
    try:
        user_id_to_unblock = int(context.args)
        response = await unblock_user(user_id_to_unblock)
        await update.message.reply_text(response)
    except (ValueError, IndexError):
        await update.message.reply_text("无效的用户ID。")

@admin_only
async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    total_users = await db.get_total_users_count()
    blocked_users = await db.get_blocked_users_count()
    
    stats_message = (
        f"机器人统计数据\n"
        f"---------------------\n"
        f"总用户数: {total_users}\n"
        f"黑名单用户数: {blocked_users}\n"
    )
    
    await update.message.reply_text(stats_message, parse_mode='Markdown')

async def getid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_type = update.effective_chat.type
    user_id = update.effective_user.id

    if chat_type == 'private':
        message = f"用户ID: `{user_id}`"
    else:
        chat_id = update.effective_chat.id
        message = (
            f"群组ID: `{chat_id}`\n"
            f"用户ID: `{user_id}`"
        )
    
    await update.message.reply_text(message, parse_mode='Markdown')