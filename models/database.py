# models/database.py — full corrected file
import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.engine import URL
from dotenv import load_dotenv

load_dotenv()

# Build the connection URL programmatically using SQLAlchemy's URL builder.
# This handles all special character encoding automatically — no manual %40 needed.
# SQLAlchemy's URL.create() takes the raw password with the literal @ symbol
# and encodes it correctly before passing to psycopg2.

def _build_database_url() -> URL:
    """
    Builds a SQLAlchemy URL object from individual .env components.
    Falls back to DATABASE_URL string if individual components aren't set.
    """
    db_user     = os.getenv("DB_USER")
    db_password = os.getenv("DB_PASSWORD")
    db_host     = os.getenv("DB_HOST")
    db_port     = os.getenv("DB_PORT", "6543")
    db_name     = os.getenv("DB_NAME", "postgres")

    if all([db_user, db_password, db_host]):
        # Use URL.create() — it handles special chars in password automatically
        return URL.create(
            drivername="postgresql+psycopg2",
            username=db_user,
            password=db_password,   # raw password — SQLAlchemy encodes it
            host=db_host,
            port=int(db_port),
            database=db_name,
        )

    # Fallback to DATABASE_URL string if individual vars not set
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise ValueError(
            "Database credentials not configured. "
            "Set DB_USER, DB_PASSWORD, DB_HOST, DB_PORT, DB_NAME in .env"
        )
    return database_url


database_url = _build_database_url()

engine = create_engine(
    database_url,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
    pool_recycle=300,
    connect_args={
        "connect_timeout": 10,
        "prepare_threshold": None,  # disables prepared statements for PgBouncer
    },
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()