from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Declarative base for all ORM models.

    Every model subclasses this so SQLAlchemy can collect the table metadata
    used by Alembic's autogenerate and by `Base.metadata.create_all`.
    """
