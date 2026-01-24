"""Redis queue monitoring logic."""

from typing import Dict, Any, Optional
from dataclasses import dataclass, asdict
from datetime import datetime

from ..queue import RedisQueue
from .db_health import DatabaseHealth


@dataclass
class QueueSnapshot:
    """Snapshot of queue states at a point in time."""

    timestamp: float
    work: int
    processing: int
    result: int
    crawling_failed: int
    saving: int
    saving_failed: int
    producer_start_time: Optional[float]
    producer_lock: Optional[str]
    total_games: int
    updated_games: int

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert to dictionary.

        Returns:
            Dictionary representation of snapshot
        """
        return asdict(self)


class QueueMonitor:
    """Monitor Redis queues for dashboard."""

    def __init__(self, redis_queue: RedisQueue, db_health: DatabaseHealth) -> None:
        """
        Initialize queue monitor.

        Args:
            redis_queue: RedisQueue instance (shared connection)
            db_health: DatabaseHealth instance for database queries
        """
        self.queue = redis_queue
        self.db_health = db_health

    def get_snapshot(self) -> QueueSnapshot:
        """
        Get current redis queue snapshot.

        Returns:
            QueueSnapshot with current queue lengths
        """

        stats = self.queue.get_all_queue_stats()
        
        # Get producer start time from Redis
        start_time_str = self.queue.client.get(self.queue.PRODUCER_START_TIME_KEY)
        start_time = float(start_time_str) if start_time_str else None

        # Query updated games count
        updated_games = self.db_health.get_updated_games_count(start_time)

        return QueueSnapshot(
            timestamp=datetime.utcnow().timestamp(),
            work=stats["work_queue_length"],
            processing=stats["processing_queue_length"],
            result=stats["result_queue_length"],
            crawling_failed=stats["crawling_failed_queue_length"],
            saving=stats["saving_queue_length"],
            saving_failed=stats["saving_failed_queue_length"],
            total_games=stats["total_games"],
            producer_start_time=stats["producer_start_time"],
            producer_lock=stats["producer_lock"],
            updated_games=updated_games
        )