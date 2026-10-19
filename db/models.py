from sqlalchemy import (
    Column, Integer, String, DateTime, Boolean, Text, ForeignKey, JSON, UniqueConstraint
)
from sqlalchemy.orm import relationship, declarative_base
from sqlalchemy.sql import func

Base = declarative_base()


class Group(Base):
    __tablename__ = "groups"

    id = Column(Integer, primary_key=True)
    name = Column(String(50), unique=True, nullable=False)
    faculty = Column(String(100))
    year = Column(String(10))
    semester = Column(String(30))
    fetched_at = Column(DateTime)

    # Параметры отчёта SSRS (берутся из AVN API)
    avn_group_id = Column(Integer)
    avn_faculty_id = Column(Integer)
    avn_year_id = Column(Integer)
    avn_semester_id = Column(Integer)
    avn_rate = Column(Integer)
    periods_json = Column(Text)

    schedule = relationship("Schedule", back_populates="group", cascade="all, delete-orphan")
    users = relationship("User", back_populates="group")


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    tg_id = Column(Integer, unique=True, nullable=False)
    login = Column(String(100), nullable=False)
    password = Column(String(255), nullable=False)
    full_name = Column(String(255))
    group_id = Column(Integer, ForeignKey("groups.id"))
    faculty = Column(String(255))
    speciality = Column(String(255))
    token = Column(Text)
    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)
    last_sync_at = Column(DateTime)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    group = relationship("Group", back_populates="users")
    grades = relationship("Grade", back_populates="user", cascade="all, delete-orphan")
    notifications = relationship("UserNotification", back_populates="user", cascade="all, delete-orphan")
    sent_notifs = relationship("NotificationLog", back_populates="user", cascade="all, delete-orphan")


class Schedule(Base):
    __tablename__ = "schedule"

    id = Column(Integer, primary_key=True)
    group_id = Column(Integer, ForeignKey("groups.id"), nullable=False)
    day_index = Column(Integer)
    day = Column(String(10))
    time_start = Column(String(10))
    time_end = Column(String(10))
    discipline = Column(String(255))
    teacher = Column(String(255))
    auditorium = Column(String(100))
    building = Column(String(100))
    lesson_type = Column(String(50))
    weeks = Column(String(50))
    raw = Column(Text)

    group = relationship("Group", back_populates="schedule")


class Grade(Base):
    __tablename__ = "grades"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    semester = Column(String(50))
    year = Column(String(20))
    discipline = Column(String(255))
    control_type = Column(String(50))
    ball = Column(String(20))
    grade = Column(String(20))
    teacher = Column(String(255))
    date = Column(String(20))
    credits = Column(String(10))
    hash_key = Column(String(64), nullable=False)
    user = relationship("User", back_populates="grades")

    __table_args__ = (UniqueConstraint("user_id", "hash_key"),)


class UserNotification(Base):
    __tablename__ = "user_notifications"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    content_hash = Column(String(64), nullable=False)
    content = Column(Text)
    user = relationship("User", back_populates="notifications")

    __table_args__ = (UniqueConstraint("user_id", "content_hash"),)


class NotificationLog(Base):
    __tablename__ = "notification_logs"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    notif_type = Column(String(50))
    content = Column(Text)
    sent_at = Column(DateTime, default=func.now())
    user = relationship("User", back_populates="sent_notifs")


class SyncState(Base):
    __tablename__ = "sync_state"

    id = Column(Integer, primary_key=True)
    key = Column(String(50), unique=True, nullable=False)
    value = Column(Text)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
