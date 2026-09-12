import logging
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.exc import OperationalError
from backend.config import settings

logger = logging.getLogger("transmute.database")

Base = declarative_base()

def get_engine():
    """
    Initializes database engine. First tries PostgreSQL settings.DATABASE_URL.
    If PostgreSQL is unreachable, falls back to SQLite so the server runs smoothly.
    """
    pg_url = settings.DATABASE_URL
    try:
        engine = create_engine(pg_url, pool_pre_ping=True)
        # Test connection
        with engine.connect() as conn:
            pass
        logger.info(f"Connected to PostgreSQL database: {pg_url}")
        return engine, pg_url
    except (OperationalError, Exception) as e:
        logger.warning(
            f"Could not connect to PostgreSQL at {pg_url} ({e}). "
            f"Falling back to local SQLite at {settings.SQLITE_FALLBACK_URL}."
        )
        sqlite_engine = create_engine(
            settings.SQLITE_FALLBACK_URL,
            connect_args={"check_same_thread": False},
        )
        return sqlite_engine, settings.SQLITE_FALLBACK_URL

engine, ACTIVE_DB_URL = get_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db():
    import backend.models  # Ensure all models are registered with Base
    Base.metadata.create_all(bind=engine)
    logger.info("Database schemas initialized.")
