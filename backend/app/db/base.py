from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


# Import all models here so Alembic can detect them
from app.models import user, disco, feeder, search, review, transaction, feeder_location  # noqa: F401, E402
