# уведомления от университета
from typing import List, Dict

from .notifications import get_notifications


async def get_university_notifications(token: str, limit: int = 50) -> List[Dict]:
    return await get_notifications(token, limit=limit)
