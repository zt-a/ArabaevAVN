import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# Тестовая БД и фиктивные настройки — должны быть заданы ДО импорта config.settings
os.environ["DB_URL"] = "sqlite:///" + os.path.join(ROOT, "test_avn.db")
os.environ.setdefault("BOT_TOKEN", "0:test")

import pytest  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _init_test_db():
    from db.database import init_db, engine
    from db.models import Base

    init_db()
    yield
    Base.metadata.drop_all(bind=engine)
    try:
        if os.path.exists(engine.url.database):
            os.remove(engine.url.database)
    except Exception:
        pass
