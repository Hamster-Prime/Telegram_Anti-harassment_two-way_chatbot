from typing import Optional
from config import config
from . import settings


def is_authorized(user_id: Optional[int]) -> bool:
    if user_id is None:
        return False

    if user_id in config.ADMIN_IDS:
        return True

    return user_id in settings.get_authorized_users()

