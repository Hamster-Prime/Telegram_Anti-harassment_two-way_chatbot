import secrets
import time

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from database import models as db
from config import config
from services.gemini_service import gemini_service

pending_verifications = {}


def _build_verification(challenge, attempts: int = 0):
    options = list(challenge.get('options') or [])
    correct_answer = challenge.get('correct_answer')
    if not options or correct_answer not in options:
        raise ValueError("Verification challenge has no selectable correct answer")

    return {
        'challenge_id': secrets.token_urlsafe(6),
        'answer': correct_answer,
        'question': challenge['question'],
        'options': options,
        'attempts': attempts,
        'created_at': time.time(),
    }


def _build_keyboard(verification):
    challenge_id = verification['challenge_id']
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                option,
                callback_data=f"verify:{challenge_id}:{index}",
            )
            for index, option in enumerate(verification['options'])
        ]
    ])

async def create_verification(user_id: int):
    challenge = await gemini_service.generate_verification_challenge()
    existing_attempts = pending_verifications.get(user_id, {}).get('attempts', 0)
    verification = _build_verification(challenge, existing_attempts)
    pending_verifications[user_id] = verification

    return (
        f"请完成人机验证: \n\n{verification['question']}",
        _build_keyboard(verification),
    )

async def verify_answer(user_id: int, challenge_id: str, option_index: int):
    if user_id not in pending_verifications:
        return False, "验证已过期或不存在。", False, None, True
    
    verification = pending_verifications[user_id]
    
    if time.time() - verification['created_at'] > config.VERIFICATION_TIMEOUT:
        del pending_verifications[user_id]
        return False, "验证超时，请重新发送消息。", False, None, False

    if challenge_id != verification['challenge_id']:
        return False, "该验证题已失效。", False, None, True

    options = verification['options']
    if option_index < 0 or option_index >= len(options):
        return False, "无效的验证选项。", False, None, True

    answer = options[option_index]
    verification['attempts'] += 1
    
    if answer == verification['answer']:
        del pending_verifications[user_id]
        await db.update_user_verification(user_id, is_verified=True)
        return True, "验证成功！", False, None, False
    
    if verification['attempts'] >= config.MAX_VERIFICATION_ATTEMPTS:
        del pending_verifications[user_id]
        
        await db.add_to_blacklist(user_id, reason="人机验证失败次数过多", blocked_by=config.BOT_ID)
        message = (
            "验证失败次数过多，您已被暂时封禁。\n\n"
            "如果您是认为误封，请重新发送消息并进行验证解除限制。"
        )
        return False, message, True, None, False
    
    challenge = await gemini_service.generate_verification_challenge()
    next_verification = _build_verification(challenge, verification['attempts'])
    pending_verifications[user_id] = next_verification

    new_question_text = f"请完成人机验证: \n\n{next_verification['question']}"
    return (
        False,
        f"答案错误，还有 {config.MAX_VERIFICATION_ATTEMPTS - verification['attempts']} 次机会。",
        False,
        (new_question_text, _build_keyboard(next_verification)),
        False,
    )

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
    
    return verification['question'], _build_keyboard(verification)
