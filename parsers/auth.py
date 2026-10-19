import httpx
from loguru import logger

BASE_URL = "https://avn.arabaev.kg/lmsnew/api"


async def login(login: str, password: str) -> dict:
    async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
        try:
            resp = await client.post(
                f"{BASE_URL}/auth/login",
                json={"login": login, "password": password},
                headers={"Content-Type": "application/json", "Accept": "application/json"},
            )
            if resp.status_code == 200:
                data = resp.json()
                if data.get("error") is False and data.get("data"):
                    return {"success": True, "token": data["data"].get("token"), "user": data["data"]}
            logger.warning(f"Login failed: {resp.status_code} {resp.text[:200]}")
            return {"success": False, "error": "Login failed"}
        except Exception as e:
            logger.error(f"Login error: {e}")
            return {"success": False, "error": str(e)}
