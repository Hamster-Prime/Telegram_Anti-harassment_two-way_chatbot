import time
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from database import models as db
from config import config
from services.gemini_service import gemini_service

pending_verifications = {}

async def create_verification(user_id: int):
    challenge = await gemini_service.generate_verification_challenge()
    question = challenge['question']
    correct_answer = challenge['correct_answer']
    options = challenge['options']
    
    existing_attempts = pending_verifications.get(user_id, {}).get('attempts', 0)
    
    pending_verifications[user_id] = {
        'answer': correct_answer,
        'question': question,
        'options': options,
        'attempts': existing_attempts,
        'created_at': time.time()
    }
    
    keyboard = [
        [InlineKeyboardButton(option, callback_data=f"verify_{option}") for option in options]
    ]
    
    return f"请完成人机验证: \n\n{question}", InlineKeyboardMarkup(keyboard)

async def verify_answer(user_id: int, answer: str):
    if user_id not in pending_verifications:
        return False, "验证已过期或不存在。", False, None
    
    verification = pending_verifications[user_id]
    
    if time.time() - verification['created_at'] > config.VERIFICATION_TIMEOUT:
        del pending_verifications[user_id]
        return False, "验证超时，请重新发送消息。", False, None
    
    verification['attempts'] += 1
    
    if answer == verification['answer']:
        del pending_verifications[user_id]
        await db.update_user_verification(user_id, is_verified=True)
        return True, "验证成功！", False, None
    
    if verification['attempts'] >= config.MAX_VERIFICATION_ATTEMPTS:
        del pending_verifications[user_id]
        
        await db.add_to_blacklist(user_id, reason="人机验证失败次数过多", blocked_by=config.BOT_ID)
        message = (
            "验证失败次数过多，您已被暂时封禁。\n\n"
            "如果您是认为误封，请重新发送消息并进行验证解除限制。"
        )
        return False, message, True, None
    
    challenge = await gemini_service.generate_verification_challenge()
    new_question = challenge['question']
    new_correct_answer = challenge['correct_answer']
    new_options = challenge['options']
    
    pending_verifications[user_id] = {
        'answer': new_correct_answer,
        'question': new_question,
        'options': new_options,
        'attempts': verification['attempts'],
        'created_at': time.time()
    }
    
    keyboard = [
        [InlineKeyboardButton(option, callback_data=f"verify_{option}") for option in new_options]
    ]
    
    new_question_text = f"请完成人机验证: \n\n{new_question}"
    return False, f"答案错误，还有 {config.MAX_VERIFICATION_ATTEMPTS - verification['attempts']} 次机会。", False, (new_question_text, InlineKeyboardMarkup(keyboard))

def is_verification_pending(user_id: int) -> tuple[bool, bool]:
    if user_id not in pending_verifications:
        return False, True
    
    verification = pending_verifications[user_id]
    is_expired = time.time() - verification['created_at'] > config.VERIFICATION_TIMEOUT
    
    if is_expired:
        del pending_verifications[user_id]
        return False, True
    
    return True, False

def get_pending_verification_message(user_id: int):
    if user_id not in pending_verifications:
        return None
    
    verification = pending_verifications[user_id]
    
    if time.time() - verification['created_at'] > config.VERIFICATION_TIMEOUT:
        del pending_verifications[user_id]
        return None
    
    question = verification['question']
    options = verification['options']
    
    keyboard = [
        [InlineKeyboardButton(option, callback_data=f"verify_{option}") for option in options]
    ]
    
    return question, InlineKeyboardMarkup(keyboard)
