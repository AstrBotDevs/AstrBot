from collections.abc import Generator
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from app.core.config import settings

SERVICE_ROOT = Path(__file__).resolve().parents[2]
DATABASE_URL = settings.resolve_sqlite_path(SERVICE_ROOT)

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    """Yield a database session for FastAPI dependencies."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _alembic_config() -> Config:
    """Load Alembic config from the fish-api service root."""
    return Config(str(SERVICE_ROOT / "alembic.ini"))


def _stamp_legacy_sqlite_if_needed() -> None:
    """One-time bridge for DBs created via create_all before Alembic."""
    if not DATABASE_URL.startswith("sqlite"):
        return
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    if "alembic_version" in tables or "users" not in tables:
        return
    cfg = _alembic_config()
    if "bot_bindings" in tables:
        cols = {c["name"] for c in inspector.get_columns("bot_bindings")}
        if "bind_status" in cols:
            command.stamp(cfg, "002_bind_status")
        else:
            command.stamp(cfg, "001_initial")
    else:
        command.stamp(cfg, "001_initial")


def init_db() -> None:
    """Apply Alembic migrations to the configured database."""
    _stamp_legacy_sqlite_if_needed()
    command.upgrade(_alembic_config(), "head")
