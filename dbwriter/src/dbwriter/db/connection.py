"""PostgreSQL database connection and session management"""

import os
from contextlib import contextmanager
from typing import Generator
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import QueuePool

from dbwriter.db.models import Base


# Database connection URL
# Format: postgresql://user:password@host:port/database
def get_database_url(
    user: str = None,
    password: str = None,
    host: str = None,
    port: str = None,
    database: str = None,
) -> str:
    """
    Get PostgreSQL connection URL from parameters or environment variables.

    Args:
        user: Database user (default: from env POSTGRES_USER or 'steam_user')
        password: Database password (default: from env POSTGRES_PASSWORD or 'steam_password')
        host: Database host (default: from env POSTGRES_HOST or 'localhost')
        port: Database port (default: from env POSTGRES_PORT or '5432')
        database: Database name (default: from env POSTGRES_DB or 'steam_games')

    Returns:
        PostgreSQL connection URL string
    """
    user = user or os.getenv("POSTGRES_USER", "steam_user")
    password = password or os.getenv("POSTGRES_PASSWORD", "steam_password")
    host = host or os.getenv("POSTGRES_HOST", "localhost")
    port = port or os.getenv("POSTGRES_PORT", "5432")
    database = database or os.getenv("POSTGRES_DB", "steam_games")

    return f"postgresql://{user}:{password}@{host}:{port}/{database}"


# Create engine with connection pooling
def create_db_engine(database_url: str = None, echo: bool = False):
    """
    Create SQLAlchemy engine with connection pooling.

    Connection Pool Settings:
    - pool_size: 5 - Maximum number of connections to keep open
    - max_overflow: 10 - Maximum number of connections to create beyond pool_size
    - pool_timeout: 30 - Seconds to wait before giving up on getting a connection
    - pool_recycle: 3600 - Recycle connections after 1 hour

    Args:
        database_url: PostgreSQL connection URL (default: from get_database_url())
        echo: Enable SQL query logging (default: False)

    Returns:
        SQLAlchemy Engine instance
    """
    if database_url is None:
        database_url = get_database_url()

    engine = create_engine(
        database_url,
        poolclass=QueuePool,
        pool_size=5,
        max_overflow=10,
        pool_timeout=30,
        pool_recycle=3600,
        echo=echo,
    )

    # Add connection pool listeners for monitoring
    @event.listens_for(engine, "connect")
    def receive_connect(dbapi_conn, connection_record):
        """Called when a new DB connection is created"""
        pass  # Can add logging here if needed

    @event.listens_for(engine, "checkout")
    def receive_checkout(dbapi_conn, connection_record, connection_proxy):
        """Called when a connection is retrieved from the pool"""
        pass  # Can add logging here if needed

    return engine


# Create session factory
_engine = None
_SessionLocal = None


def init_db(database_url: str = None, echo: bool = False):
    """
    Initialize database engine and create all tables.

    This function should be called once when the application starts.

    Args:
        database_url: PostgreSQL connection URL (default: from get_database_url())
        echo: Enable SQL query logging (default: False)
    """
    global _engine, _SessionLocal

    _engine = create_db_engine(database_url, echo)
    _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_engine)

    # Create all tables
    Base.metadata.create_all(bind=_engine)


def get_session() -> Session:
    """
    Get a new database session.

    Returns:
        SQLAlchemy Session instance
    """
    if _SessionLocal is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    return _SessionLocal()


@contextmanager
def get_session_context() -> Generator[Session, None, None]:
    """
    Context manager for database sessions.

    Automatically commits on success and rolls back on error.

    Yields:
        SQLAlchemy Session instance
    """
    session = get_session()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def drop_all_tables(database_url: str = None):
    """
    Drop all tables from the database.

    WARNING: This will delete all data!

    Args:
        database_url: PostgreSQL connection URL (default: from get_database_url())
    """
    if database_url is None:
        database_url = get_database_url()

    engine = create_engine(database_url)
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def get_engine():
    """
    Get the current database engine.

    Returns:
        SQLAlchemy Engine instance

    Raises:
        RuntimeError: If database is not initialized
    """
    if _engine is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    return _engine
