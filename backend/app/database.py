import enum
import logging
import time
from collections.abc import Generator
from pathlib import Path

from sqlalchemy import Enum, create_engine, event, text
from sqlalchemy.exc import OperationalError, TimeoutError as SATimeoutError
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

_DB_RETRY_ATTEMPTS = 3
_DB_RETRY_DELAY_SECONDS = 0.75


def sa_enum(enum_class: type[enum.Enum]) -> Enum:
    """PostgreSQL enums use lowercase values (admin), not Python names (ADMIN)."""
    return Enum(enum_class, values_callable=lambda x: [e.value for e in x])


def _is_sqlite() -> bool:
    return settings.DATABASE_URL.startswith("sqlite")


def _is_postgres() -> bool:
    return settings.DATABASE_URL.startswith("postgresql")


connect_args: dict = {"check_same_thread": False} if _is_sqlite() else {"connect_timeout": 8}
if _is_postgres():
    connect_args.update(
        {
            "keepalives": 1,
            "keepalives_idle": 30,
            "keepalives_interval": 10,
            "keepalives_count": 5,
        }
    )

engine_kwargs: dict = {
    "connect_args": connect_args,
    "pool_pre_ping": True,
    "pool_reset_on_return": "rollback",
}
if _is_postgres():
    engine_kwargs.update(
        {
            "pool_size": 10,
            "max_overflow": 15,
            "pool_recycle": 300,
            "pool_timeout": 5,
        }
    )

engine = create_engine(settings.DATABASE_URL, **engine_kwargs)


if _is_postgres():

    @event.listens_for(engine, "connect")
    def set_postgres_session_timeouts(dbapi_connection, _connection_record):
        # Neon pooler rejects statement_timeout in startup options — set after connect.
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("SET statement_timeout = '15000'")
            cursor.execute("SET lock_timeout = '8000'")
        except Exception as exc:
            logger.debug("Could not set Postgres session timeouts: %s", exc)
        finally:
            cursor.close()


def _sqlite_path_from_url(url: str) -> Path | None:
    if not url.startswith("sqlite:///"):
        return None
    raw = url[len("sqlite:///") :]
    return Path(raw) if raw.startswith("/") else Path(raw)


def _ensure_sqlite_directory() -> None:
    if not _is_sqlite():
        return
    db_path = _sqlite_path_from_url(settings.DATABASE_URL)
    if db_path is None:
        return
    db_path.parent.mkdir(parents=True, exist_ok=True)


_ensure_sqlite_directory()


if _is_sqlite():

    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA temp_store=MEMORY")
        cursor.execute("PRAGMA cache_size=-64000")
        cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def invalidate_pool() -> None:
    """Drop pooled connections after Neon/network drops an idle socket."""
    try:
        engine.dispose()
    except Exception as exc:
        logger.warning("Failed to dispose DB pool: %s", exc)


def with_db_retry(fn, /, *, retries: int = _DB_RETRY_ATTEMPTS):
    """Run a DB write callback in a fresh session, retrying on Neon/network drops."""
    last_exc: Exception | None = None
    for attempt in range(retries):
        db = SessionLocal()
        try:
            result = fn(db)
            db.commit()
            return result
        except OperationalError as exc:
            last_exc = exc
            try:
                db.rollback()
            except Exception:
                pass
            invalidate_pool()
            if attempt < retries - 1:
                time.sleep(_DB_RETRY_DELAY_SECONDS * (attempt + 1))
        finally:
            try:
                db.close()
            except Exception:
                pass
    assert last_exc is not None
    raise last_exc


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    except (OperationalError, SATimeoutError):
        try:
            db.rollback()
        except Exception:
            pass
        invalidate_pool()
        raise
    finally:
        try:
            db.close()
        except Exception:
            pass


def check_database_connection() -> bool:
    db = None
    try:
        db = SessionLocal()
        db.execute(text("SELECT 1"))
        return True
    except (OperationalError, SATimeoutError):
        invalidate_pool()
        return False
    finally:
        if db is not None:
            try:
                db.close()
            except Exception:
                pass
