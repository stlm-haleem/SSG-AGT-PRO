import datetime as dt
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text
from database import Base


def now():
    return dt.datetime.utcnow()


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=False)
    role = Column(String, nullable=False, default="Viewer")
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=now)
    # ISO timestamp (with the generating PC's UTC offset) of this user's most recent Generate Summary
    last_generate_at = Column(String, nullable=True)


class Role(Base):
    """Custom roles with per-page / per-action permissions."""
    __tablename__ = "roles"
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False, index=True)
    permissions = Column(Text, default="[]")  # JSON list of permission keys
    created_at = Column(DateTime, default=now)
