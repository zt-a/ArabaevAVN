import httpx
from loguru import logger
from typing import Dict, List

from .common import BASE_URL, auth_kwargs, check_status, AuthError


async def _get(token: str, path: str) -> Dict:
    async with httpx.AsyncClient(follow_redirects=True, timeout=60.0) as client:
        try:
            resp = await client.get(f"{BASE_URL}{path}", **auth_kwargs(token))
            check_status(resp)
            if resp.status_code == 200:
                return resp.json()
            logger.warning(f"Attendance fetch {path} failed: {resp.status_code}")
            return {}
        except AuthError:
            raise
        except Exception as e:
            logger.error(f"Attendance error {path}: {e}")
            return {}


async def get_user_diagram(token: str) -> Dict:
    """Сводка: рейтинг, оценки, посещаемость. Возвращает dict с ключами."""
    data = await _get(token, "/setting/user-diagram")
    if not data or data.get("error") or not data.get("data"):
        return {}
    parts = data["data"]
    result = {
        "rating": None,
        "payment": None,
        "grades_summary": [],
        "attendance": [],
    }
    if len(parts) > 0 and parts[0]:
        result["rating"] = parts[0][0] if isinstance(parts[0], list) else parts[0]
    if len(parts) > 1 and parts[1]:
        result["payment"] = parts[1][0] if isinstance(parts[1], list) else parts[1]
    if len(parts) > 2 and isinstance(parts[2], list):
        result["grades_summary"] = parts[2]
    if len(parts) > 3 and isinstance(parts[3], list):
        result["attendance"] = parts[3]
    return result


def attendance_percent(attendance: List[Dict]) -> float:
    """
    % посещаемости из строк вида:
      {"posetil": 0, "kol_pos": 9,  "Percentvisit": "47,37", "name_pos": "Посетил"}
      {"posetil": 1, "kol_pos": 10, "Percentvisit": "52,63", "name_pos": "Не посещал"}
    posetil=0 -> посещённые, posetil=1 -> пропущенные.
    """
    if not attendance:
        return 0.0
    for a in attendance:
        if a.get("posetil") == 0 or a.get("name_pos") == "Посетил":
            p = a.get("Percentvisit")
            if p not in (None, ""):
                try:
                    return round(float(str(p).replace(",", ".")), 1)
                except ValueError:
                    pass
    total = sum(int(a.get("kol_pos", 0) or 0) for a in attendance)
    visited = sum(int(a.get("kol_pos", 0) or 0) for a in attendance if a.get("posetil") == 0)
    if total == 0:
        return 0.0
    return round(visited * 100.0 / total, 1)


def attendance_risk_message(percent: float) -> str:
    """Предупреждение о риске н/а (неудовлетворительно) по посещаемости."""
    if percent >= 75:
        return ""
    if percent >= 50:
        return (
            f"⚠️ Посещаемость: {percent}%. Это ниже 75%. "
            f"Если пропуски продолжатся, возможна итоговая н/а по некоторым дисциплинам."
        )
    if percent >= 25:
        return (
            f"🚨 КРИТИЧЕСКАЯ посещаемость: {percent}%. "
            f"Высокий риск получить н/а (неудовлетворительно) по дисциплинам с ограничением посещаемости. "
            f"Обратитесь к куратору/деканату."
        )
    return (
        f"🆘 КРИТИЧЕСКАЯ посещаемость: {percent}%. "
        f"С высокой вероятностью будет н/а (неудовлетворительно) по дисциплинам с ограничением посещаемости. "
        f"Срочно обратитесь к куратору или в деканат."
    )
