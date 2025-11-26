from datetime import datetime, timedelta, timezone
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
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
        "- `/view_filtered` - 查看被拦截信息及发送者\n"
        "- `/exempt` - 豁免用户内容审查（临时或永久）\n"
    )
    
    await update.message.reply_text(help_text, parse_mode='Markdown')

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
        user_id_to_unblock = int(context.args[0])
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
        f"黑名单用户数: {blocked_users}\n\n"
        f"请选择要查看的列表："
    )
    
    keyboard = [
        [InlineKeyboardButton("所有用户列表", callback_data="stats_list_all_users_page_1")],
        [InlineKeyboardButton("黑名单用户列表", callback_data="stats_list_blacklist_page_1")]
    ]
    
    await update.message.reply_text(
        stats_message, 
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

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

@admin_only
async def panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    total_users = await db.get_total_users_count()
    blocked_users = await db.get_blocked_users_count()
    exempted_users = await db.get_exemptions_count()
    is_enabled = await db.get_autoreply_enabled()
    
    message = (
        f"管理面板\n\n"
        f"统计信息:\n\n"
        f"总用户数: {total_users}\n"
        f"黑名单用户数: {blocked_users}\n"
        f"豁免用户数: {exempted_users}\n"
        f"自动回复状态: {'已启用' if is_enabled else '已禁用'}\n\n"
        f"请选择要查看的功能："
    )
    
    keyboard = [
        [InlineKeyboardButton("黑名单管理", callback_data="panel_blacklist_page_1"), InlineKeyboardButton("所有用户信息", callback_data="panel_stats")],
        [InlineKeyboardButton("被过滤消息", callback_data="panel_filtered_page_1"), InlineKeyboardButton("自动回复管理", callback_data="panel_autoreply")],
        [InlineKeyboardButton("豁免名单管理", callback_data="panel_exemptions_page_1"), InlineKeyboardButton("网络测试管理", callback_data="panel_network_test")],
        [InlineKeyboardButton("RSS 功能管理", callback_data="panel_rss")],
    ]
    
    await update.message.reply_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

@admin_only
async def exempt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    admin_id = update.effective_user.id
    
    if message.is_topic_message:
        thread_id = message.message_thread_id
        user_to_exempt = await db.get_user_by_thread_id(thread_id)
        
        if not user_to_exempt:
            await update.message.reply_text("无法找到该话题对应的用户。")
            return
        
        user_id_to_exempt = user_to_exempt['user_id']
        
        if not context.args:
            exemption_info = await db.get_exemption(user_id_to_exempt)
            if exemption_info:
                is_permanent = bool(exemption_info.get('is_permanent', 0))
                expires_at = exemption_info.get('expires_at')
                reason = exemption_info.get('reason', '无')
                
                status_text = "永久豁免" if is_permanent else f"临时豁免（到期时间: {expires_at}）"
                await update.message.reply_text(
                    f"用户 {user_id_to_exempt} 当前状态: {status_text}\n"
                    f"原因: {reason}\n\n"
                    f"用法:\n"
                    f"/exempt permanent [reason] - 永久豁免\n"
                    f"/exempt temp <小时数> [reason] - 临时豁免（例如: /exempt temp 24）\n"
                    f"/exempt remove - 移除豁免"
                )
            else:
                await update.message.reply_text(
                    f"用户 {user_id_to_exempt} 当前未被豁免。\n\n"
                    f"用法:\n"
                    f"/exempt permanent [reason] - 永久豁免\n"
                    f"/exempt temp <小时数> [reason] - 临时豁免（例如: /exempt temp 24）\n"
                    f"/exempt remove - 移除豁免"
                )
            return
        
        subcommand = context.args[0].lower()
        
        if subcommand == "remove":
            await db.remove_exemption(user_id_to_exempt)
            await update.message.reply_text(f"已移除用户 {user_id_to_exempt} 的内容审查豁免。")
            return
        
        reason = " ".join(context.args[1:]) if len(context.args) > 1 else "管理员豁免"
        
        if subcommand == "permanent":
            await db.add_exemption(user_id_to_exempt, is_permanent=True, exempted_by=admin_id, reason=reason)
            await update.message.reply_text(
                f"用户 {user_id_to_exempt} 已被永久豁免内容审查。\n原因: {reason}"
            )
        elif subcommand == "temp":
            if len(context.args) < 2:
                await update.message.reply_text("请指定临时豁免的小时数。用法: /exempt temp <小时数> [reason]")
                return
            
            try:
                hours = int(context.args[1])
                expires_at = (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat()
                reason = " ".join(context.args[2:]) if len(context.args) > 2 else "管理员临时豁免"
                
                await db.add_exemption(user_id_to_exempt, is_permanent=False, exempted_by=admin_id, reason=reason, expires_at=expires_at)
                await update.message.reply_text(
                    f"用户 {user_id_to_exempt} 已被临时豁免内容审查 {hours} 小时。\n原因: {reason}"
                )
            except ValueError:
                await update.message.reply_text("无效的小时数。请提供数字。")
        else:
            await update.message.reply_text(
                "无效的子命令。用法:\n"
                "/exempt permanent [reason] - 永久豁免\n"
                "/exempt temp <小时数> [reason] - 临时豁免\n"
                "/exempt remove - 移除豁免"
            )
        return
    
    if not context.args:
        await update.message.reply_text(
            "请提供用户ID或在话题中发送命令。\n\n"
            "用法:\n"
            "在话题中: /exempt [permanent|temp <小时数>|remove] [reason]\n"
            "直接使用: /exempt <user_id> [permanent|temp <小时数>|remove] [reason]"
        )
        return
    
    try:
        user_id_to_exempt = int(context.args[0])
        
        if len(context.args) < 2:
            exemption_info = await db.get_exemption(user_id_to_exempt)
            if exemption_info:
                is_permanent = bool(exemption_info.get('is_permanent', 0))
                expires_at = exemption_info.get('expires_at')
                reason = exemption_info.get('reason', '无')
                
                status_text = "永久豁免" if is_permanent else f"临时豁免（到期时间: {expires_at}）"
                await update.message.reply_text(
                    f"用户 {user_id_to_exempt} 当前状态: {status_text}\n原因: {reason}"
                )
            else:
                await update.message.reply_text(f"用户 {user_id_to_exempt} 当前未被豁免。")
            return
        
        subcommand = context.args[1].lower()
        reason = " ".join(context.args[2:]) if len(context.args) > 2 else "管理员豁免"
        
        if subcommand == "remove":
            await db.remove_exemption(user_id_to_exempt)
            await update.message.reply_text(f"已移除用户 {user_id_to_exempt} 的内容审查豁免。")
        elif subcommand == "permanent":
            await db.add_exemption(user_id_to_exempt, is_permanent=True, exempted_by=admin_id, reason=reason)
            await update.message.reply_text(
                f"用户 {user_id_to_exempt} 已被永久豁免内容审查。\n原因: {reason}"
            )
        elif subcommand == "temp":
            if len(context.args) < 3:
                await update.message.reply_text("请指定临时豁免的小时数。用法: /exempt <user_id> temp <小时数> [reason]")
                return
            
            try:
                hours = int(context.args[2])
                expires_at = (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat()
                reason = " ".join(context.args[3:]) if len(context.args) > 3 else "管理员临时豁免"
                
                await db.add_exemption(user_id_to_exempt, is_permanent=False, exempted_by=admin_id, reason=reason, expires_at=expires_at)
                await update.message.reply_text(
                    f"用户 {user_id_to_exempt} 已被临时豁免内容审查 {hours} 小时。\n原因: {reason}"
                )
            except ValueError:
                await update.message.reply_text("无效的小时数。请提供数字。")
        else:
            await update.message.reply_text(
                "无效的子命令。用法:\n"
                "/exempt <user_id> permanent [reason] - 永久豁免\n"
                "/exempt <user_id> temp <小时数> [reason] - 临时豁免\n"
                "/exempt <user_id> remove - 移除豁免"
            )
    except (ValueError, IndexError):
        await update.message.reply_text("无效的用户ID。")

@admin_only
async def autoreply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        is_enabled = await db.get_autoreply_enabled()
        status_text = "已启用" if is_enabled else "已禁用"
        
        message = (
            f"自动回复管理\n\n"
            f"当前状态: {status_text}\n\n"
            f"请选择操作："
        )
        
        keyboard = [
            [
                InlineKeyboardButton(
                    "关闭自动回复" if is_enabled else "开启自动回复",
                    callback_data=f"autoreply_toggle"
                )
            ],
            [InlineKeyboardButton("管理知识库", callback_data="autoreply_kb_list_page_1")],
            [InlineKeyboardButton("添加知识条目", callback_data="autoreply_kb_add")],
        ]
        
        await update.message.reply_text(
            message,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        return
    
    subcommand = context.args[0].lower()
    
    if subcommand == "on":
        await db.set_autoreply_enabled(True)
        await update.message.reply_text("自动回复已开启")
    elif subcommand == "off":
        await db.set_autoreply_enabled(False)
        await update.message.reply_text("自动回复已关闭")
    elif subcommand == "add":
        if len(context.args) < 3:
            await update.message.reply_text(
                "用法: /autoreply add <标题> <内容>\n\n"
                "示例: /autoreply add 常见问题 这是问题的答案"
            )
            return
        
        title = context.args[1]
        content = " ".join(context.args[2:])
        await db.add_knowledge_entry(title, content)
        await update.message.reply_text(f"已添加知识条目: {title}")
    elif subcommand == "list":
        entries = await db.get_all_knowledge_entries()
        if not entries:
            await update.message.reply_text("知识库为空")
            return
        
        message = "知识库条目:\n\n"
        for entry in entries:
            message += f"ID: {entry['id']}\n"
            message += f"标题: {entry['title']}\n"
            message += f"内容: {entry['content'][:50]}...\n\n"
        
        await update.message.reply_text(message)
    elif subcommand == "edit":
        if len(context.args) < 4:
            await update.message.reply_text(
                "用法: /autoreply edit <ID> <标题> <内容>\n\n"
                "示例: /autoreply edit 1 新标题 新内容"
            )
            return
        
        try:
            entry_id = int(context.args[1])
        except ValueError:
            await update.message.reply_text("无效的条目ID")
            return
        
        title = context.args[2]
        content = " ".join(context.args[3:])
        
        entry = await db.get_knowledge_entry(entry_id)
        if not entry:
            await update.message.reply_text(f"条目ID {entry_id} 不存在")
            return
        
        await db.update_knowledge_entry(entry_id, title, content)
        await update.message.reply_text(f"已更新知识条目: {title}")
    elif subcommand == "delete":
        if len(context.args) < 2:
            await update.message.reply_text("用法: /autoreply delete <ID>")
            return
        
        try:
            entry_id = int(context.args[1])
        except ValueError:
            await update.message.reply_text("无效的条目ID")
            return
        
        entry = await db.get_knowledge_entry(entry_id)
        if not entry:
            await update.message.reply_text(f"条目ID {entry_id} 不存在")
            return
        
        await db.delete_knowledge_entry(entry_id)
        await update.message.reply_text(f"已删除知识条目: {entry['title']}")
    else:
        await update.message.reply_text(
            "用法:\n"
            "/autoreply - 显示管理菜单\n"
            "/autoreply on - 开启自动回复\n"
            "/autoreply off - 关闭自动回复\n"
            "/autoreply add <标题> <内容> - 添加知识条目\n"
            "/autoreply edit <ID> <标题> <内容> - 编辑知识条目\n"
            "/autoreply delete <ID> - 删除知识条目\n"
            "/autoreply list - 列出所有知识条目"
        )
