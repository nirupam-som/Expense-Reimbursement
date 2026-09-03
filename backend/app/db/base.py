"""Declarative base for every ORM model.

Models import Base from here; Alembic imports this module's metadata for autogenerate.
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
