import httpx
from loguru import logger

BASE_URL = "https://avn.arabaev.kg/lmsnew/api"


class AuthError(Exception):
    """Токен AVN отсутствует/просрочен (HTTP 401)."""


def auth_kwargs(token: str) -> dict:
    """
    AVN API принимает JWT как cookie `token`, а не как Bearer-заголовок.
    Отправляем оба варианта для надёжности.
    """
    return {
        "headers": {
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
        },
        "cookies": {"token": token},
    }


def new_client(timeout: float = 30.0) -> httpx.AsyncClient:
    return httpx.AsyncClient(follow_redirects=True, timeout=timeout)


def check_status(resp: httpx.Response) -> None:
    if resp.status_code == 401:
        logger.warning("AVN 401: token expired")
        raise AuthError("token expired")
    if resp.status_code != 200:
        logger.warning(f"AVN HTTP {resp.status_code}")
