"""Redis queue management for Producer-Consumer pattern."""

import os
import json
import time
import logging
import ssl
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv
import redis

# Load environment variables
load_dotenv()

# Set logger from parent
logger = logging.getLogger(__name__)

class RedisQueue:
    """
    Redis queue manager for Steam-Spider Producer.
    Manages queue and key.
    """

    # Redis queue names
    WORK_QUEUE = "queue:work"
    RESULT_QUEUE = "queue:result"

    # Additional queues for monitoring
    PROCESSING_QUEUE = "queue:processing"
    SAVING_QUEUE = "queue:saving"
    CRAWLING_FALIED_QUEUE = "dlq:crawling" 
    SAVING_FAILED_QUEUE = "dlq:db_insert"

    # Additional keys
    LOCK_KEY = "lock:producer"
    TOTAL_GAMES_KEY = "stats:total_games"
    PRODUCER_START_TIME_KEY = "stats:producer_start_time"

    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        db: Optional[int] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        decode_responses: bool = False
    ):
        """
        Initialize Redis connection.

        Args:
            host: Redis host (default: from REDIS_HOST env or 'localhost')
            port: Redis port (default: from REDIS_PORT env or 6379)
            db: Redis database number (default: from REDIS_DB env or 0)
            user_name: Redis username (default: from REDIS_PRODUCER_MONITOR_ID env or None)
            password: Redis password (default: from REDIS_PRODUCER_MONITOR_PW env or None)
            decode_responses: Decode responses as strings (default: False for binary safety)
        """
        self.host = host or os.getenv("REDIS_HOST", "localhost")
        self.port = int(port or os.getenv("REDIS_PORT", 6379))
        self.db = int(db or os.getenv("REDIS_DB", 0))
        self.username = username or os.getenv("REDIS_ID_PRODUCER_MONITOR")
        self.password = password or os.getenv("REDIS_PW_PRODUCER_MONITOR")

        # TLS/SSL Configuration
        ssl_enabled = os.getenv("REDIS_SSL_ENABLED", "false").lower() == "true"
        connection_kwargs = {
            "host": self.host,
            "port": self.port,
            "db": self.db,
            "username": self.username,
            "password": self.password,
            "decode_responses": decode_responses
        }

        if ssl_enabled:
            ssl_ca_cert = os.getenv("REDIS_SSL_CA_CERT")
            ssl_cert = os.getenv("REDIS_SSL_CERT")
            ssl_key = os.getenv("REDIS_SSL_KEY")
            ssl_check_hostname = os.getenv("REDIS_SSL_CHECK_HOSTNAME", "false").lower() == "true"

            logger.info(f"Enabling TLS connection | CA={ssl_ca_cert}")
            connection_kwargs["ssl"] = True
            connection_kwargs["ssl_cert_reqs"] = ssl.CERT_REQUIRED

            if ssl_ca_cert:
                connection_kwargs["ssl_ca_certs"] = ssl_ca_cert
            if ssl_cert:
                connection_kwargs["ssl_certfile"] = ssl_cert
            if ssl_key:
                connection_kwargs["ssl_keyfile"] = ssl_key

            connection_kwargs["ssl_check_hostname"] = ssl_check_hostname

        self.client = redis.Redis(**connection_kwargs)

        # Test connection
        try:
            self.client.ping()
            logger.info(f"✓ Connected to Redis at {self.host}:{self.port} (DB: {self.db})")
        except redis.ConnectionError as e:
            # logger.error(f"❌ Failed to connect to Redis: {e}")
            raise ConnectionError(f"Failed to connect to Redis: {e}")

    def push_jobs(
        self,
        game_ids: List[int],
        batch_size: int = 2000,
        retry_count: int = 0,
        base_delay: float = 1.5,
        add_to_total: bool = True
    ) -> int:
        """
        Push game IDs to work queue in batches.

        Args:
            game_ids: List of Steam game IDs to process
            batch_size: Number of IDs to push per batch (default: 2000)
            retry_count: Initial retry count for jobs (default: 0)
            base_delay: Base delay between requests in seconds (default: 1.5)

        Returns:
            Total number of jobs pushed

        Examples:
            >>> queue = RedisQueue()
            >>> queue.push_jobs([1091500, 1091499, 1091498])
            >>> # Pushes 3 jobs to queue:work
        """
        total_pushed = 0
        batch_count = 0

        logger.info(f"Pushing {len(game_ids)} jobs to Redis queue...")

        # Process in batches
        for i in range(0, len(game_ids), batch_size):
            batch = game_ids[i:i + batch_size]
            batch_count += 1

            # Create job payloads
            jobs = []
            for game_id in batch:
                job = {
                    "game_id": game_id,
                    "retry_count": retry_count,
                    "base_delay": base_delay,
                    "created_at": time.time()
                }
                jobs.append(json.dumps(job))

            if jobs:
                self.client.lpush(self.WORK_QUEUE, *jobs)
                total_pushed += len(jobs)
                if add_to_total:
                    self.add_total_games(len(jobs))
                logger.debug(f"  Batch {batch_count}: Pushed {len(jobs)} jobs (Total: {total_pushed})")

        logger.info(f"✓ Completed! Total jobs pushed: {total_pushed}")
        return total_pushed
    
    def release_producer_lock(self) -> None:
        """Force release the producer lock."""
        try:
            self.client.delete(self.LOCK_KEY)
            logger.info(f"🔒 Lock '{self.LOCK_KEY}' released successfully.")
        except Exception as e:
            logger.warning(f"⚠ Failed to release lock: {e}")

    def set_total_games(self, total: int) -> None:
        """
        Store total game count for progress calculation.

        Args:
            total: Total number of games to process
        """
        self.client.set(self.TOTAL_GAMES_KEY, total)

    def add_total_games(self, more: int) -> None:
        """
        Add to total game count for progress calculation.

        Args:
            more: Number of games to add
        """
        try:
            current_total = self.get_total_games()
            self.set_total_games(current_total + more)
            logger.info(f"📊 Added {more} to total games in Redis")
        except Exception as e:
            logger.warning(f"⚠ Failed to add total games: {e}")   

    def set_producer_start_time(self) -> None:
        """Record the start time of the producer."""
        try:
            self.client.set(self.PRODUCER_START_TIME_KEY, str(time.time()))
            logger.info(f"📊 Recorded producer start time in Redis")
        except Exception as e:
            logger.warning(f"⚠ Failed to record start time: {e}")

    # Get queue length
    def get_work_queue_length(self) -> int:
        return self.client.llen(self.WORK_QUEUE)
    def get_result_queue_length(self) -> int:
        return self.client.llen(self.RESULT_QUEUE)
    def get_processing_queue_length(self) -> int:
        return self.client.llen(self.PROCESSING_QUEUE)
    def get_crawling_failed_queue_length(self) -> int:
        return self.client.llen(self.CRAWLING_FALIED_QUEUE)
    def get_saving_queue_length(self) -> int:
        return self.client.llen(self.SAVING_QUEUE)
    def get_saving_failed_queue_length(self) -> int:
        return self.client.llen(self.SAVING_FAILED_QUEUE)

    def get_total_games(self) -> int:
        value = self.client.get(self.TOTAL_GAMES_KEY)
        return int(value) if value else 0

    def get_queue_stats(self) -> Dict[str, Any]:
        return {
            "work_queue_length": self.get_work_queue_length(),
            "result_queue_length": self.get_result_queue_length(),
        }

    def get_all_queue_stats(self) -> Dict[str, Any]:
        """
        Get all queue statistics using pipeline.

        Returns:
            Dictionary containing all queue stats:
                - work_queue_length: Jobs waiting to be processed
                - processing_queue_length: Jobs currently being processed
                - result_queue_length: Results waiting to be written to DB
                - crawling_failed_queue_length: Failed jobs (max retries exceeded or cannot crawl)
                - saving_queue_length: Jobs currently being written to DB
                - saving_failed_queue_length: Failed to write to DB
                - total_games: Total number of games to process
                - producer_start_time: Producer start time
                - producer_lock: Lock status
        """
        pipe = self.client.pipeline()
        pipe.llen(self.WORK_QUEUE)
        pipe.llen(self.PROCESSING_QUEUE)
        pipe.llen(self.RESULT_QUEUE)
        pipe.llen(self.CRAWLING_FALIED_QUEUE)
        pipe.llen(self.SAVING_QUEUE)
        pipe.llen(self.SAVING_FAILED_QUEUE)
        pipe.get(self.TOTAL_GAMES_KEY)
        pipe.get(self.PRODUCER_START_TIME_KEY)
        pipe.get(self.LOCK_KEY)
        results = pipe.execute()

        return {
            "work_queue_length": int(results[0]) if results[0] else 0,
            "processing_queue_length": int(results[1]) if results[1] else 0,
            "result_queue_length": int(results[2]) if results[2] else 0,
            "crawling_failed_queue_length": int(results[3]) if results[3] else 0,
            "saving_queue_length": int(results[4]) if results[4] else 0,
            "saving_failed_queue_length": int(results[5]) if results[5] else 0,
            "total_games": int(results[6]) if results[6] else 0,
            "producer_start_time": float(results[7]) if results[7] else 0,
            "producer_lock": results[8]
        }
    # Clear data

    def clear_work_queue(self) -> None:
        self.client.delete(self.WORK_QUEUE)
        logger.info(f"✓ Cleared {self.WORK_QUEUE}")
    def clear_processing_queue(self) -> None:
        self.client.delete(self.PROCESSING_QUEUE)
        logger.info(f"✓ Cleared {self.PROCESSING_QUEUE}")
    def clear_result_queue(self) -> None:
        self.client.delete(self.RESULT_QUEUE)
        logger.info(f"✓ Cleared {self.RESULT_QUEUE}")
    def clear_crawling_failed_queue(self) -> None:
        self.client.delete(self.CRAWLING_FALIED_QUEUE)
        logger.info(f"✓ Cleared {self.CRAWLING_FALIED_QUEUE}")
    def clear_saving_queue(self) -> None:
        self.client.delete(self.SAVING_QUEUE)
        logger.info(f"✓ Cleared {self.SAVING_QUEUE}")
    def clear_saving_failed_queue(self) -> None:
        self.client.delete(self.SAVING_FAILED_QUEUE)
        logger.info(f"✓ Cleared {self.SAVING_FAILED_QUEUE}")
    def clear_total_games(self) -> None:
        self.client.delete(self.TOTAL_GAMES_KEY)
        logger.info(f"✓ Cleared {self.TOTAL_GAMES_KEY}")
    def clear_producer_start_time(self) -> None:
        self.client.delete(self.PRODUCER_START_TIME_KEY)
        logger.info(f"✓ Cleared {self.PRODUCER_START_TIME_KEY}")
    def clear_failed_jobs(self) -> None:
        self.clear_crawling_failed_queue()
        self.clear_saving_failed_queue()
        logger.info(f"✓ Cleared failed jobs")

    def clear_all(self, release_lock: bool = True) -> None:
        """Clear all queues, sets, and counters. Use with extreme caution!"""
        self.clear_work_queue()
        self.clear_processing_queue()
        self.clear_result_queue()
        self.clear_crawling_failed_queue()
        self.clear_saving_queue()
        self.clear_saving_failed_queue()
        self.clear_total_games()
        self.clear_producer_start_time()
        if release_lock:
            self.release_producer_lock()
        logger.info("✓ Cleared all Redis keys")

    def recover_processing_queue(self) -> int:
        recovered = 0
        while True:
            job = self.client.rpop(self.PROCESSING_QUEUE)
            if not job:
                break
            self.client.lpush(self.WORK_QUEUE, job)
            recovered += 1
        return recovered

    def close(self) -> None:
        """Close Redis connection."""
        self.client.close()
        logger.info("✓ Closed Redis connection")
    
    def get_failed_crawling_data(self, start_index: int = 0, end_index: int = -1) -> List[Dict[str, Any]]:
        raw_data_list = self.client.lrange(self.CRAWLING_FALIED_QUEUE, start_index, end_index)
        data_list = [json.loads(data) for data in raw_data_list]
        return data_list
    
    def get_failed_insert_data(self, start_index: int = 0, end_index: int = -1) -> List[Dict[str, Any]]:
        raw_data_list = self.client.lrange(self.SAVING_FAILED_QUEUE, start_index, end_index)
        data_list = [json.loads(data) for data in raw_data_list]
        return data_list

    def get_processing_data(self, start_index: int = 0, end_index: int = -1) -> List[Dict[str, Any]]:
        raw_data_list = self.client.lrange(self.PROCESSING_QUEUE, start_index, end_index)
        data_list = [json.loads(data) for data in raw_data_list]
        return data_list

    def get_saving_data(self, start_index: int = 0, end_index: int = -1) -> List[Dict[str, Any]]:
        raw_data_list = self.client.lrange(self.SAVING_QUEUE, start_index, end_index)
        data_list = [json.loads(data) for data in raw_data_list]
        return data_list

    def get_failed_ids(self) -> List[int]:
        data_list = []
        data_list.extend(self.get_failed_crawling_data())
        data_list.extend(self.get_failed_insert_data())
        data_ids = [int(data["game_id"]) for data in data_list if data.get("game_id")]
        return data_ids
    
    def push_failed_jobs(self, reset_failed_jobs: bool = True) -> None:
        game_ids = self.get_failed_ids()
        if not game_ids:
            return
        self.push_jobs(game_ids = game_ids,add_to_total=False)
        if reset_failed_jobs:
            self.clear_failed_jobs()

    def get_processing_ids(self) -> List[int]:
        """Extract game_ids from processing and saving queues."""
        data_list = []
        data_list.extend(self.get_processing_data())
        data_list.extend(self.get_saving_data())
        data_ids = [int(data["game_id"]) for data in data_list if data.get("game_id")]
        return data_ids

    def push_processing_jobs(self, reset_processing_jobs: bool = True) -> None:
        """Re-queue jobs from processing and saving queues back to work queue."""
        game_ids = self.get_processing_ids()
        if not game_ids:
            return
        self.push_jobs(game_ids=game_ids, add_to_total=False)
        if reset_processing_jobs:
            self.clear_processing_queue()
            self.clear_saving_queue()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()