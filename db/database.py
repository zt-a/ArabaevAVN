from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from loguru import logger
from .models import Base
from config.settings import settings

engine = create_engine(settings.DB_URL, echo=False, connect_args={"check_same_thread": False} if "sqlite" in settings.DB_URL else {})
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, expire_on_commit=False)

# Колонки, добавленные после первичного релиза: (таблица, колонка, DDL-тип)
_MIGRATIONS = [
    ("groups", "avn_group_id", "INTEGER"),
    ("groups", "avn_faculty_id", "INTEGER"),
    ("groups", "avn_year_id", "INTEGER"),
    ("groups", "avn_semester_id", "INTEGER"),
    ("groups", "avn_rate", "INTEGER"),
    ("groups", "periods_json", "TEXT"),
]


def _migrate():
    if "sqlite" not in settings.DB_URL:
        return
    with engine.begin() as conn:
        for table, column, ddl in _MIGRATIONS:
            cols = {row[1] for row in conn.execute(text(f"PRAGMA table_info({table})"))}
            if not cols:
                continue
            if column not in cols:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))
                logger.info(f"Migration: added {table}.{column}")


def init_db():
    Base.metadata.create_all(bind=engine)
    _migrate()
