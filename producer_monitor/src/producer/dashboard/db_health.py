"""PostgreSQL database health check."""

from typing import Dict, Any, Optional
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
import logging

logger = logging.getLogger(__name__)


class DatabaseHealth:
    """PostgreSQL database health checker."""

    def __init__(self, database_url: str) -> None:
        """
        Initialize database health checker.

        Args:
            database_url: PostgreSQL connection URL
        """
        self.database_url = database_url
        self.engine: Optional[Any] = None

    def check(self) -> Dict[str, Any]:
        """
        Check database connection and get table counts.

        Returns:
            Dictionary with:
                - connected: bool
                - version: str (PostgreSQL version)
                - tables: dict with table row counts
                - error: str (if connection failed)
        """
        try:
            if self.engine is None:
                self.engine = create_engine(
                    self.database_url,
                    pool_size=2,
                    max_overflow=0,
                    pool_pre_ping=True
                )

            with self.engine.connect() as conn:
                # Get PostgreSQL version
                version_result = conn.execute(text("SELECT version()"))
                version = version_result.scalar()
                version_short = version.split(",")[0] if version else "Unknown"

                # Get table counts
                tables = {}
                for table_name in ["basic_info", "genres", "tags", "reviews"]:
                    try:
                        result = conn.execute(text(f"SELECT COUNT(*) FROM {table_name}"))
                        tables[table_name] = result.scalar()
                    except Exception as e:
                        logger.warning(f"Failed to count {table_name}: {e}")
                        tables[table_name] = -1

                return {
                    "connected": True,
                    "version": version_short,
                    "tables": tables,
                    "error": None
                }

        except OperationalError as e:
            logger.error(f"Database connection failed: {e}")
            return {
                "connected": False,
                "version": None,
                "tables": {},
                "error": str(e)
            }

    def get_updated_games_count(self, start_time: Optional[float]) -> int:
        """
        Count games updated since the given start time.

        Args:
            start_time: Unix timestamp of producer start (None if not started)

        Returns:
            Number of games updated since start_time, or 0 if no start time
        """
        if start_time is None:
            return 0

        try:
            if self.engine is None:
                self.engine = create_engine(
                    self.database_url,
                    pool_size=2,
                    max_overflow=0,
                    pool_pre_ping=True
                )

            with self.engine.connect() as conn:
                # Convert unix timestamp to PostgreSQL timestamp
                query = text("""
                    SELECT COUNT(*)
                    FROM basic_info
                    WHERE updated_at >= to_timestamp(:start_time)
                """)
                result = conn.execute(query, {"start_time": start_time})
                count = result.scalar()
                return count if count else 0
        except Exception as e:
            logger.error(f"Failed to query updated games count: {e}")
            return 0

    def close(self) -> None:
        """Close database connection."""
        if self.engine:
            self.engine.dispose()
