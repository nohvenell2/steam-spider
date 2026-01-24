"""Batch processing logic for DB Writer"""

import time
import logging
import random
import json
from typing import Dict, Any, List, Tuple
from sqlalchemy.exc import IntegrityError, OperationalError

from dbwriter.config import Config
from dbwriter.date_parser import DateParser
from dbwriter.data_validator import DataValidator
from dbwriter.db.connection import get_session_context
from dbwriter.db.crud import bulk_insert_games
from dbwriter.exceptions import DatabaseConnectionError

logger = logging.getLogger(__name__)


def transform_data(raw_data: Dict[str, Any], date_parser: DateParser) -> Dict[str, Any]:
    """
    Transform raw data from Redis queue to database format.
    Called in main.py before adding to buffer.

    Key transformations:
    1. Parse release_date string to datetime object
    2. Validate and sanitize data (auto-truncate long fields)

    Args:
        raw_data: Raw game data from queue:result
        date_parser: DateParser instance for parsing release dates

    Returns:
        Transformed and sanitized data ready for database insertion
    """
    game_id = raw_data.get("game_id")

    # Parse release_date string to datetime
    release_date_string = raw_data.get("release_date")
    parsed_date = date_parser.parse(release_date_string, game_id=game_id)

    # Build transformed data
    transformed = {
        "game_id": game_id,
        "url": raw_data.get("url"),
        "title": raw_data.get("title"),
        "description": raw_data.get("description"),
        "header_image": raw_data.get("header_image"),
        "developer": raw_data.get("developer"),
        "publisher": raw_data.get("publisher"),
        "release_date": parsed_date,  # datetime object or None
        "release_date_original": release_date_string,  # original string from Steam
        "genres": raw_data.get("genres", []),
        "tags": raw_data.get("tags", []),
        "reviews": raw_data.get("reviews", {}),
    }

    # Validate and sanitize (auto-truncate fields exceeding DB limits)
    sanitized = DataValidator.validate_and_sanitize(transformed)

    return sanitized


class BatchProcessor:
    """
    Batch processor for game data.

    Manages buffer of game data and performs bulk insert to PostgreSQL
    when buffer is full or timeout is reached.
    """

    def __init__(self, config: Config, redis_client):
        """
        Initialize batch processor.

        Args:
            config: Configuration object
            redis_client: Redis client for queue cleanup operations
        """
        self.config = config
        self.redis_client = redis_client
        self.buffer: List[tuple[Dict[str, Any], str]] = []
        self.buffer_size = config.BUFFER_SIZE
        self.buffer_timeout = config.BUFFER_TIMEOUT
        self.last_insert_time = time.time()
        self.date_parser = DateParser()  # Keep for backward compatibility

        # Statistics
        self.total_processed = 0
        self.total_inserted = 0
        self.total_failed = 0

        logger.info(
            f"BatchProcessor initialized | buffer_size={self.buffer_size} | timeout={self.buffer_timeout}s"
        )

    def add_to_buffer(self, transformed_data: Dict[str, Any], raw_json: str):
        """
        Add pre-transformed data and raw JSON to buffer.

        Args:
            transformed_data: Already transformed and validated game data
            raw_json: Original JSON string from Redis (for LREM operation)
        """
        try:
            # Store both the transformed data and raw JSON for cleanup
            self.buffer.append((transformed_data, raw_json))

            # Check if flush is needed
            if self.should_flush():
                self.flush_buffer()

        except Exception as e:
            game_id = transformed_data.get("game_id", "unknown")
            logger.error(f"Failed to add to buffer | game_id={game_id} | error={str(e)}")
            self.total_failed += 1

    def should_flush(self) -> bool:
        """
        Check if buffer should be flushed.

        Returns:
            True if buffer size >= limit OR timeout expired
        """
        size_exceeded = len(self.buffer) >= self.buffer_size
        timeout_exceeded = (time.time() - self.last_insert_time) >= self.buffer_timeout

        return size_exceeded or timeout_exceeded

    def flush_buffer(self):
        """
        Flush buffer to PostgreSQL database with Redis cleanup.

        CRITICAL ORDER:
        1. Extract DB data and raw JSON strings from buffer
        2. Perform DB insert with retry logic
        3. ONLY AFTER DB SUCCESS: Remove messages from queue:saving
        4. If LREM fails: Log warning (messages will be reprocessed)
        """
        if not self.buffer:
            return

        buffer_count = len(self.buffer)
        start_time = time.time()

        try:
            # Separate transformed data from raw JSON strings
            games_data = [item[0] for item in self.buffer]
            raw_json_list = [item[1] for item in self.buffer]

            # Perform bulk insert with retry
            inserted_count, failed_savings = self._bulk_insert_with_retry(games_data)

            # Log failed games
            if failed_savings:
                self._log_failures_to_redis(failed_savings)

            # CRITICAL: DB insert successful - now clean up queue:saving
            cleanup_success = self._cleanup_queue_saving(raw_json_list)

            duration = time.time() - start_time
            self.total_processed += buffer_count
            self.total_inserted += inserted_count

            if cleanup_success:
                logger.info(
                    f"Buffer flushed | count={buffer_count} | inserted={inserted_count} | "
                    f"queue_cleaned={len(raw_json_list)} | duration={duration:.2f}s | total={self.total_processed}"
                )
            else:
                logger.warning(
                    f"Buffer flushed but queue cleanup incomplete | count={buffer_count} | "
                    f"inserted={inserted_count} | duration={duration:.2f}s | "
                    f"WARNING: Some messages may be reprocessed"
                )

            # Clear buffer and update timestamp
            self.buffer.clear()
            self.last_insert_time = time.time()

        except Exception as e:
            logger.error(f"Buffer flush failed | count={buffer_count} | error={str(e)}")
            self.total_failed += buffer_count
            # Clear buffer to avoid infinite retry
            self.buffer.clear()
            self.last_insert_time = time.time()
            raise

    def _cleanup_queue_saving(self, raw_json_list: List[str]) -> bool:
        """
        Remove successfully processed messages from queue:saving using Redis Pipeline.

        Implements retry logic for transient Redis failures.
        Messages that fail to be removed will be reprocessed (safe due to upsert logic).

        Args:
            raw_json_list: List of raw JSON strings to remove from queue:saving

        Returns:
            True if cleanup successful, False otherwise
        """
        if not raw_json_list:
            return True

        max_retries = 3
        base_delay = 0.5

        for attempt in range(1, max_retries + 1):
            try:
                # Use Pipeline for batch LREM operations (non-transactional)
                pipeline = self.redis_client.pipeline(transaction=False)

                for raw_json in raw_json_list:
                    # LREM queue:saving 1 <raw_json>
                    # Count=1: Remove first occurrence from left
                    pipeline.lrem("queue:saving", 1, raw_json)

                # Execute pipeline - returns list of removed counts
                results = pipeline.execute()

                # Check results: each LREM returns number of elements removed
                failed_removals = []
                for idx, removed_count in enumerate(results):
                    if removed_count == 0:
                        # Message not found (already removed or never existed)
                        game_id = "unknown"
                        try:
                            data = json.loads(raw_json_list[idx])
                            game_id = data.get("game_id", "unknown")
                        except:
                            pass
                        failed_removals.append(game_id)

                if failed_removals:
                    logger.warning(
                        f"Some messages not found in queue:saving | count={len(failed_removals)} | "
                        f"game_ids={failed_removals[:5]} | reason=already_removed_or_missing"
                    )

                # Consider successful if pipeline executed
                logger.info(
                    f"Queue cleanup completed | removed={len([r for r in results if r > 0])} | "
                    f"not_found={len(failed_removals)} | attempt={attempt}"
                )
                return True

            except Exception as e:
                if attempt == max_retries:
                    logger.error(
                        f"Queue cleanup failed after {max_retries} attempts | "
                        f"count={len(raw_json_list)} | error={str(e)} | "
                        f"WARNING: Messages will be reprocessed on next run"
                    )
                    return False

                delay = base_delay * attempt
                logger.warning(
                    f"Queue cleanup failed | retry={attempt}/{max_retries} | "
                    f"delay={delay}s | error={str(e)}"
                )
                time.sleep(delay)

        return False

    def _bulk_insert_with_retry(self, games_data: List[Dict[str, Any]]) -> Tuple[int, List[Dict[str, Any]]]:
        """
        Perform bulk insert with exponential backoff retry.

        Args:
            games_data: List of transformed game data dictionaries

        Returns:
            Number of successfully inserted games

        Raises:
            DatabaseConnectionError: If max retries exceeded
        """
        max_retries = self.config.MAX_DB_RETRIES
        base_delay = self.config.RETRY_BASE_DELAY
        max_delay = self.config.RETRY_MAX_DELAY

        for attempt in range(1, max_retries + 1):
            try:
                with get_session_context() as session:
                    count, failed_savings = bulk_insert_games(session, games_data)
                    return count, failed_savings


            except IntegrityError as e:
                # Duplicate key - log warning and skip
                logger.warning(f"Integrity error (duplicate keys?) | error={str(e)}")
                return 0, [{"error": str(e), "data": "batch_error"}] # Return 0 as no new games were inserted

            except OperationalError as e:
                # Database connection/operation error
                if attempt == max_retries:
                    logger.error(
                        f"Database operation failed after {max_retries} retries | error={str(e)}"
                    )
                    raise DatabaseConnectionError(f"Max retries exceeded: {str(e)}")

                # Calculate delay with exponential backoff and jitter
                delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
                jitter = random.uniform(0, delay * 0.1)
                total_delay = delay + jitter

                logger.warning(
                    f"Database operation failed | retry={attempt}/{max_retries} | "
                    f"delay={total_delay:.1f}s | error={str(e)}"
                )
                time.sleep(total_delay)

            except Exception as e:
                # Unexpected error
                logger.error(f"Unexpected error during bulk insert | error={str(e)}")
                raise

        # Should not reach here
        raise DatabaseConnectionError("Bulk insert failed unexpectedly")

    def get_statistics(self) -> Dict[str, int]:
        """
        Get processing statistics.

        Returns:
            Dictionary with statistics
        """
        return {
            "total_processed": self.total_processed,
            "total_inserted": self.total_inserted,
            "total_failed": self.total_failed,
            "buffer_size": len(self.buffer),
        }
    
    def _log_failures_to_redis(self, failed_savings: List[Dict[str, Any]]):
        """
        Save failed game information to db in redis

        Args:
            failed_savings: List of failed game information
        """
        try:
            pipeline = self.redis_client.pipeline()
            for failure in failed_savings:
                error_data = json.dumps(failure, default=str, ensure_ascii=False)
                pipeline.rpush("dlq:db_insert", error_data)
            pipeline.execute()
            logger.info(f"Logged {len(failed_savings)} failed games to dlq:db_insert")
        except Exception as e:
            logger.error(f"Failed to log errors to Redis | error={str(e)}")
            pass
