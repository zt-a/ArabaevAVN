import httpx
from loguru import logger
from typing import Dict

from .common import BASE_URL, auth_kwargs, check_status, AuthError


async def get_userinfo(token: str) -> Dict:
    async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
        try:
            resp = await client.get(f"{BASE_URL}/setting/user-info", **auth_kwargs(token))
            check_status(resp)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("error") is False and data.get("data"):
                    return data["data"][0] if data["data"] else {}
            logger.warning(f"Userinfo returned no data: {resp.status_code}")
            return {}
        except AuthError:
            raise
        except Exception as e:
            logger.error(f"Userinfo error: {e}")
            return {}
