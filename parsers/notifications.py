import httpx
from loguru import logger
from typing import List, Dict

from .common import BASE_URL, auth_kwargs, check_status, AuthError


async def get_notifications(token: str, limit: int = 20) -> List[Dict]:
    async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
        try:
            resp = await client.post(
                f"{BASE_URL}/notification/list",
                **auth_kwargs(token),
                json={"page": 1, "limit": limit},
            )
            check_status(resp)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("error") is False and data.get("data"):
                    if isinstance(data["data"], list) and data["data"] and isinstance(data["data"][0], list):
                        return data["data"][0]
                    return data["data"]
            logger.warning(f"Notifications returned no data: {resp.status_code}")
            return []
        except AuthError:
            raise
        except Exception as e:
            logger.error(f"Notifications error: {e}")
            return []
