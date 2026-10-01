"""The Flask extensions, made once and bound to the app in create_app."""

from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


db = SQLAlchemy(model_class=Base)
migrate = Migrate()
# The client address only lives in the limiter's counters, never in the
# database.
limiter = Limiter(key_func=get_remote_address, default_limits=[])
