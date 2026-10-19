import hashlib
import json
import httpx
from loguru import logger
from typing import List, Dict

from .common import BASE_URL, auth_kwargs, check_status, AuthError


async def get_transcript(token: str) -> List[Dict]:
    async with httpx.AsyncClient(follow_redirects=True, timeout=60.0) as client:
        try:
            resp = await client.get(f"{BASE_URL}/setting/transcript", **auth_kwargs(token))
            check_status(resp)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("error") is False and data.get("data"):
                    return data["data"]
            logger.warning(f"Transcript returned no data: {resp.status_code}")
            return []
        except AuthError:
            raise
        except Exception as e:
            logger.error(f"Transcript error: {e}")
            return []


def make_hash(item: Dict) -> str:
    key_str = json.dumps(item, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(key_str.encode()).hexdigest()
