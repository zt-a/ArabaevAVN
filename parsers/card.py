import httpx
from loguru import logger
from typing import List, Dict

from .common import BASE_URL, auth_kwargs, check_status, AuthError


async def get_study_card(token: str) -> List[Dict]:
    async with httpx.AsyncClient(follow_redirects=True, timeout=60.0) as client:
        try:
            resp = await client.get(f"{BASE_URL}/card/study-card", **auth_kwargs(token))
            check_status(resp)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("error") is False:
                    return data.get("data", [])
            logger.warning(f"Study card returned no data: {resp.status_code}")
            return []
        except AuthError:
            raise
        except Exception as e:
            logger.error(f"Study card error: {e}")
            return []


def parse_grades(card: List[Dict]) -> List[Dict]:
    """Список оценок из строк study-card (дисциплина + форма контроля + балл)."""
    grades: List[Dict] = []
    for row in card or []:
        if not isinstance(row, dict):
            continue
        discipline = (row.get("p34") or "").strip()
        if not discipline:
            continue
        grades.append({
            "semester": (row.get("p42") or "").strip(),
            "year": (row.get("p32") or "").strip(),
            "discipline": discipline,
            "control_type": (row.get("p30") or "").strip(),
            "ball": str(row.get("ball") if row.get("ball") is not None else ""),
            "grade": (row.get("p31") or "").strip(),
            "teacher": (row.get("t_fio") or row.get("s_t_fio") or "").strip(),
            "date": (row.get("p36") or "").strip(),
            "credits": str(row.get("kredits") if row.get("kredits") is not None else ""),
        })
    return grades
