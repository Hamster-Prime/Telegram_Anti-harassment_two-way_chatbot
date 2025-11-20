import re
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest
from telegram.ext import ContextTypes
from services.verification import verify_answer, create_verification
from services.gemini_service import gemini_service
from database import models as db
from utils.media_converter import sticker_to_image
from services.thread_manager import get_or_create_thread
from .user_handler import _resend_message

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    user_id = query.from_user.id
    
    if data.startswith("verify_"):
        answer = data.split("_", 1)[1]
        success, message, is_banned, new_question = await verify_answer(user_id, answer)
        
        if is_banned:
            await query.edit_message_text(text=message, reply_markup=None)
            return
        
        if new_question:
            new_question_text, new_keyboard = new_question
            await query.edit_message_text(
                text=f"{message}\n\n{new_question_text}",
                reply_markup=new_keyboard
            )
            return
        
        await query.edit_message_text(text=message)

        if success:
            if 'pending_update' in context.user_data:
                pending_update = context.user_data.pop('pending_update')
                message = pending_update.message
                image_bytes = None

                if message.photo:
                    photo_file = await message.photo[-1].get_file()
                    image_bytes = await photo_file.download_as_bytearray()
                elif message.sticker and not message.sticker.is_animated and not message.sticker.is_video:
                    sticker_file = await message.sticker.get_file()
                    sticker_bytes = await sticker_file.download_as_bytearray()
                    image_bytes = await sticker_to_image(sticker_bytes)

                should_forward = True
                if message.video or message.animation:
                    pass
                else:
                    analyzing_message = await context.bot.send_message(
                        chat_id=message.chat_id,
                        text="正在通过AI分析内容是否包含垃圾信息...",
                        reply_to_message_id=message.message_id
                    )
                    analysis_result = await gemini_service.analyze_message(message, image_bytes)
                    if analysis_result.get("is_spam"):
                        should_forward = False
                        media_type = None
                        media_file_id = None
                        if message.photo:
                            media_type = "photo"
                            media_file_id = message.photo[-1].file_id
                        elif message.sticker:
                            media_type = "sticker"
                            media_file_id = message.sticker.file_id

                        await db.save_filtered_message(
                            user_id=user_id,
                            message_id=message.message_id,
                            content=message.text or message.caption,
                            reason=analysis_result.get("reason"),
                            media_type=media_type,
                            media_file_id=media_file_id,
                        )
                        reason = analysis_result.get("reason", "未提供原因")
                        await analyzing_message.edit_text(f"您的消息已被系统拦截，因此未被转发\n\n原因：{reason}")
                    else:
                        await analyzing_message.delete()

                if should_forward:
                    thread_id, is_new = await get_or_create_thread(pending_update, context)
                    if not thread_id:
                        await pending_update.message.reply_text("无法创建或找到您的话题，请联系管理员。")
                        return
                    
                    try:
                        if not is_new:
                            await _resend_message(pending_update, context, thread_id)
                    except BadRequest as e:
                        if "Message thread not found" in e.message:
                            await db.update_user_thread_id(user_id, None)
                            await db.update_user_verification(user_id, False)
                            
                            context.user_data['pending_update'] = pending_update
                            question, keyboard = await create_verification(user_id)
                            
                            full_message = (
                                "您的话题已被关闭，请重新进行验证以发送消息。\n\n"
                                f"{question}"
                            )
                            
                            await pending_update.message.reply_text(
                                text=full_message,
                                reply_markup=keyboard
                            )
                        else:
                            print(f"发送消息时发生未知错误: {e}")
                            await pending_update.message.reply_text("发送消息时发生未知错误，请稍后再试。")
            else:
                await query.message.reply_text("现在您可以发送消息了！")
    
    elif data.startswith("unblock_"):
        from services.blacklist import verify_unblock_answer
        answer = data.split("_", 1)[1]
        message, success = await verify_unblock_answer(user_id, answer)
        
        await query.edit_message_text(text=message, reply_markup=None)
        
    elif data.startswith("admin_unblock_"):
        from services import blacklist
        
        user_id_to_unblock = int(data.split("_")[2])
        
        if not await db.is_admin(user_id):
            await query.answer("抱歉，您没有权限执行此操作。", show_alert=True)
            return
            
        response = await blacklist.unblock_user(user_id_to_unblock)
        await query.answer(response, show_alert=True)

        current_page = 1
        message_text = query.message.text or ""
        is_stats_page = "黑名单用户列表" in message_text or "stats_list_blacklist" in str(query.message.reply_markup)
        
        if "第" in message_text and "/" in message_text:
            try:
                match = re.search(r'第\s*(\d+)/', message_text)
                if match:
                    current_page = int(match.group(1))
            except:
                pass
        
        if is_stats_page:
            message, keyboard = await blacklist.get_blacklist_keyboard_detailed(page=current_page)
        else:
            message, keyboard = await blacklist.get_blacklist_keyboard(page=current_page)
        
        if keyboard:
            await query.edit_message_text(
                text=message,
                reply_markup=keyboard,
                parse_mode='Markdown'
            )
        else:
            await query.edit_message_text(text=message)
    
    elif data.startswith("blacklist_page_"):
        from services import blacklist
        
        if not await db.is_admin(user_id):
            await query.answer("抱歉，您没有权限执行此操作。", show_alert=True)
            return
        
        try:
            page = int(data.split("_")[2])
        except (ValueError, IndexError):
            await query.answer("无效的页码。", show_alert=True)
            return
        
        message, keyboard = await blacklist.get_blacklist_keyboard(page=page)
        if keyboard:
            await query.edit_message_text(
                text=message,
                reply_markup=keyboard,
                parse_mode='Markdown'
            )
        else:
            await query.edit_message_text(text=message)
    
    elif data.startswith("filtered_page_"):
        from .admin_handler import _format_filtered_messages, _get_filtered_messages_keyboard
        
        if not await db.is_admin(user_id):
            await query.answer("抱歉，您没有权限执行此操作。", show_alert=True)
            return
        
        try:
            page = int(data.split("_")[2])
        except (ValueError, IndexError):
            await query.answer("无效的页码。", show_alert=True)
            return
        
        MESSAGES_PER_PAGE = 5

        total_count = await db.get_filtered_messages_count()
        
        if total_count == 0:
            await query.edit_message_text("没有找到被过滤的消息。")
            return
        
        total_pages = (total_count + MESSAGES_PER_PAGE - 1) // MESSAGES_PER_PAGE

        if page < 1:
            page = 1
        elif page > total_pages:
            page = total_pages

        offset = (page - 1) * MESSAGES_PER_PAGE

        messages = await db.get_filtered_messages(MESSAGES_PER_PAGE, offset)
        
        if not messages:
            await query.edit_message_text("没有找到被过滤的消息。")
            return

        response = await _format_filtered_messages(messages, page, total_pages)

        keyboard = await _get_filtered_messages_keyboard(page, total_pages)

        if keyboard:
            await query.edit_message_text(response, reply_markup=keyboard)
        else:
            await query.edit_message_text(response)
    
    elif data.startswith("stats_list_all_users_page_"):
        from services.blacklist import get_all_users_keyboard
        
        if not await db.is_admin(user_id):
            await query.answer("抱歉，您没有权限执行此操作。", show_alert=True)
            return
        
        try:
            page = int(data.split("_")[5])
        except (ValueError, IndexError):
            await query.answer("无效的页码。", show_alert=True)
            return
        
        message, keyboard = await get_all_users_keyboard(page=page)
        if keyboard:
            await query.edit_message_text(
                text=message,
                reply_markup=keyboard,
                parse_mode='Markdown'
            )
        else:
            await query.edit_message_text(text=message, parse_mode='Markdown')
    
    elif data.startswith("stats_list_blacklist_page_"):
        from services.blacklist import get_blacklist_keyboard_detailed
        
        if not await db.is_admin(user_id):
            await query.answer("抱歉，您没有权限执行此操作。", show_alert=True)
            return
        
        try:
            page = int(data.split("_")[4])
        except (ValueError, IndexError):
            await query.answer("无效的页码。", show_alert=True)
            return
        
        message, keyboard = await get_blacklist_keyboard_detailed(page=page)
        if keyboard:
            await query.edit_message_text(
                text=message,
                reply_markup=keyboard,
                parse_mode='Markdown'
            )
        else:
            await query.edit_message_text(text=message, parse_mode='Markdown')
    
    elif data == "stats_back_to_menu":
        from .command_handler import stats
        
        if not await db.is_admin(user_id):
            await query.answer("抱歉，您没有权限执行此操作。", show_alert=True)
            return
        
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
        
        await query.edit_message_text(
            text=stats_message,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    
    elif data.startswith("autoreply_"):
        if not await db.is_admin(user_id):
            await query.answer("抱歉，您没有权限执行此操作。", show_alert=True)
            return
        
        if data == "autoreply_toggle":
            is_enabled = await db.get_autoreply_enabled()
            await db.set_autoreply_enabled(not is_enabled)
            new_status = "已启用" if not is_enabled else "已禁用"
            await query.answer(f"自动回复已{new_status}", show_alert=True)
            
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
                        callback_data="autoreply_toggle"
                    )
                ],
                [InlineKeyboardButton("管理知识库", callback_data="autoreply_kb_list_page_1")],
                [InlineKeyboardButton("添加知识条目", callback_data="autoreply_kb_add")],
            ]
            
            await query.edit_message_text(
                message,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
        
        elif data.startswith("autoreply_kb_list_page_"):
            try:
                page = int(data.split("_")[4])
            except (ValueError, IndexError):
                page = 1
            
            entries = await db.get_all_knowledge_entries()
            if not entries:
                await query.edit_message_text("知识库为空")
                return
            
            MESSAGES_PER_PAGE = 5
            total_pages = (len(entries) + MESSAGES_PER_PAGE - 1) // MESSAGES_PER_PAGE
            if page < 1:
                page = 1
            elif page > total_pages:
                page = total_pages
            
            start_idx = (page - 1) * MESSAGES_PER_PAGE
            end_idx = start_idx + MESSAGES_PER_PAGE
            page_entries = entries[start_idx:end_idx]
            
            message = f"知识库条目 (第 {page}/{total_pages} 页)\n\n"
            keyboard = []
            
            for entry in page_entries:
                title = entry['title'][:30] + "..." if len(entry['title']) > 30 else entry['title']
                keyboard.append([
                    InlineKeyboardButton(
                        f"{title}",
                        callback_data=f"autoreply_kb_view_{entry['id']}"
                    )
                ])
                keyboard.append([
                    InlineKeyboardButton(
                        "编辑",
                        callback_data=f"autoreply_kb_edit_{entry['id']}"
                    ),
                    InlineKeyboardButton(
                        "删除",
                        callback_data=f"autoreply_kb_delete_{entry['id']}"
                    )
                ])
            
            nav_buttons = []
            if page > 1:
                nav_buttons.append(InlineKeyboardButton("上一页", callback_data=f"autoreply_kb_list_page_{page-1}"))
            if page < total_pages:
                nav_buttons.append(InlineKeyboardButton("下一页", callback_data=f"autoreply_kb_list_page_{page+1}"))
            if nav_buttons:
                keyboard.append(nav_buttons)
            
            keyboard.append([InlineKeyboardButton("返回", callback_data="autoreply_back")])
            
            await query.edit_message_text(
                message,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
        
        elif data.startswith("autoreply_kb_view_"):
            try:
                entry_id = int(data.split("_")[3])
            except (ValueError, IndexError):
                await query.answer("无效的条目ID", show_alert=True)
                return
            
            entry = await db.get_knowledge_entry(entry_id)
            if not entry:
                await query.answer("条目不存在", show_alert=True)
                return
            
            message = (
                f"知识条目详情\n\n"
                f"ID: {entry['id']}\n"
                f"标题: {entry['title']}\n"
                f"内容: {entry['content']}\n\n"
                f"创建时间: {entry['created_at']}\n"
                f"更新时间: {entry['updated_at']}"
            )
            
            keyboard = [
                [
                    InlineKeyboardButton("编辑", callback_data=f"autoreply_kb_edit_{entry_id}"),
                    InlineKeyboardButton("删除", callback_data=f"autoreply_kb_delete_{entry_id}")
                ],
                [InlineKeyboardButton("返回列表", callback_data="autoreply_kb_list_page_1")]
            ]
            
            await query.edit_message_text(
                message,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
        
        elif data.startswith("autoreply_kb_edit_"):
            try:
                entry_id = int(data.split("_")[3])
            except (ValueError, IndexError):
                await query.answer("无效的条目ID", show_alert=True)
                return
            
            entry = await db.get_knowledge_entry(entry_id)
            if not entry:
                await query.answer("条目不存在", show_alert=True)
                return
            
            await query.edit_message_text(
                f"编辑知识条目\n\n"
                f"ID: {entry['id']}\n"
                f"标题: {entry['title']}\n"
                f"内容: {entry['content']}\n\n"
                f"请使用以下格式发送编辑命令：\n"
                f"`/autoreply edit {entry_id} <新标题> <新内容>`\n\n"
                f"示例：\n"
                f"`/autoreply edit {entry_id} 新标题 新内容`",
                parse_mode='Markdown'
            )
        
        elif data.startswith("autoreply_kb_delete_"):
            try:
                entry_id = int(data.split("_")[3])
            except (ValueError, IndexError):
                await query.answer("无效的条目ID", show_alert=True)
                return
            
            entry = await db.get_knowledge_entry(entry_id)
            if not entry:
                await query.answer("条目不存在", show_alert=True)
                return
            
            await db.delete_knowledge_entry(entry_id)
            await query.answer(f"已删除: {entry['title']}", show_alert=True)
            
            entries = await db.get_all_knowledge_entries()
            if not entries:
                await query.edit_message_text("知识库为空")
                return
            
            page = 1
            MESSAGES_PER_PAGE = 5
            total_pages = (len(entries) + MESSAGES_PER_PAGE - 1) // MESSAGES_PER_PAGE
            
            start_idx = (page - 1) * MESSAGES_PER_PAGE
            end_idx = start_idx + MESSAGES_PER_PAGE
            page_entries = entries[start_idx:end_idx]
            
            message = f"知识库条目 (第 {page}/{total_pages} 页)\n\n"
            keyboard = []
            
            for entry in page_entries:
                title = entry['title'][:30] + "..." if len(entry['title']) > 30 else entry['title']
                keyboard.append([
                    InlineKeyboardButton(
                        f"{title}",
                        callback_data=f"autoreply_kb_view_{entry['id']}"
                    )
                ])
                keyboard.append([
                    InlineKeyboardButton(
                        "编辑",
                        callback_data=f"autoreply_kb_edit_{entry['id']}"
                    ),
                    InlineKeyboardButton(
                        "删除",
                        callback_data=f"autoreply_kb_delete_{entry['id']}"
                    )
                ])
            
            nav_buttons = []
            if page < total_pages:
                nav_buttons.append(InlineKeyboardButton("下一页", callback_data=f"autoreply_kb_list_page_{page+1}"))
            if nav_buttons:
                keyboard.append(nav_buttons)
            
            keyboard.append([InlineKeyboardButton("返回", callback_data="autoreply_back")])
            
            await query.edit_message_text(
                message,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
        
        elif data == "autoreply_back":
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
                        callback_data="autoreply_toggle"
                    )
                ],
                [InlineKeyboardButton("管理知识库", callback_data="autoreply_kb_list_page_1")],
                [InlineKeyboardButton("添加知识条目", callback_data="autoreply_kb_add")],
            ]
            
            await query.edit_message_text(
                message,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
        
        elif data == "autoreply_kb_add":
            await query.edit_message_text(
                "添加知识条目\n\n"
                "请使用以下格式发送新条目：\n"
                "`/autoreply add <标题> <内容>`\n\n"
                "示例：\n"
                "`/autoreply add 常见问题 这是问题的答案`",
                parse_mode='Markdown'
            )