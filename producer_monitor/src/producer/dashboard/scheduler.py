"""Automation scheduler for continuous crawling cycles."""

import os
import subprocess
import threading
import time
import logging
from enum import Enum
from typing import Optional, Dict, Any
from dataclasses import dataclass, asdict

from sqlalchemy import create_engine, text

from ..queue import RedisQueue
from .db_health import DatabaseHealth
from .admin import start_producer

logger = logging.getLogger(__name__)


class SchedulerState(Enum):
    """Scheduler state machine states."""
    IDLE = "idle"
    WAITING_COMPLETION = "waiting_completion"
    RETRYING_FAILED = "retrying_failed"
    WAITING_RETRY_COMPLETION = "waiting_retry_completion"
    CLONING_DB = "cloning_db"
    STARTING_PRODUCER = "starting_producer"
    ERROR = "error"


@dataclass
class SchedulerStatus:
    """Thread-safe snapshot of scheduler state."""
    state: str
    running: bool
    cycle_count: int
    last_state_change: Optional[float]
    last_error: Optional[str]
    config: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# Redis lock keys for clone/embedding coordination
CLONE_LOCK_KEY = "lock:db_clone"
EMBEDDING_LOCK_KEY = "lock:embedding"
CLONE_LOCK_TTL = 3600  # 1 hour


class AutomationScheduler:
    """
    Automation scheduler that runs a continuous cycle:
    1. Wait for all jobs to complete
    2. Retry failed/processing jobs, wait again
    3. Clone database (pg_dump|psql approach with Redis lock)
    4. Reset Redis, start new producer
    5. Repeat
    """

    def __init__(
        self,
        redis_queue: RedisQueue,
        db_health: DatabaseHealth,
        producer_mode: str = "test",
        producer_sample_count: int = 100,
        poll_interval: int = 10,
        clone_db_name: str = "steam_games_clone",
        max_wait_time: int = 432000,
        db_host: str = "localhost",
        db_port: int = 5432,
        db_user: str = "steam_user",
        db_password: str = "steam_password",
        db_name: str = "steam_games",
    ):
        self._redis_queue = redis_queue
        self._db_health = db_health
        self._producer_mode = producer_mode
        self._producer_sample_count = producer_sample_count
        self._poll_interval = poll_interval
        self._clone_db_name = clone_db_name
        self._max_wait_time = max_wait_time  # 120 hours default
        self._db_host = db_host
        self._db_port = db_port
        self._db_user = db_user
        self._db_password = db_password
        self._db_name = db_name

        self._state = SchedulerState.IDLE
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._cycle_count = 0
        self._last_state_change: Optional[float] = None
        self._last_error: Optional[str] = None

        if self._clone_db_name:
            self._verify_pg_tools()

    def start(self) -> bool:
        """Start the scheduler. Returns False if already running."""
        with self._lock:
            if self._running:
                return False
            self._running = True
            self._stop_event.clear()
            self._last_error = None
            self._transition(SchedulerState.WAITING_COMPLETION)

        self._thread = threading.Thread(
            target=self._run, daemon=True, name="AutomationScheduler"
        )
        self._thread.start()
        logger.info("[Scheduler] Started")
        return True

    def stop(self) -> bool:
        """Stop the scheduler. Returns False if not running."""
        with self._lock:
            if not self._running:
                return False
            self._running = False
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=30)
        with self._lock:
            self._transition(SchedulerState.IDLE)
        logger.info("[Scheduler] Stopped")
        return True

    def get_status(self) -> SchedulerStatus:
        """Get thread-safe snapshot of scheduler state."""
        with self._lock:
            return SchedulerStatus(
                state=self._state.value,
                running=self._running,
                cycle_count=self._cycle_count,
                last_state_change=self._last_state_change,
                last_error=self._last_error,
                config={
                    "producer_mode": self._producer_mode,
                    "producer_sample_count": self._producer_sample_count,
                    "poll_interval": self._poll_interval,
                    "clone_db_name": self._clone_db_name,
                },
            )

    def _transition(self, new_state: SchedulerState) -> None:
        """Transition to new state. Must be called while holding self._lock."""
        old = self._state
        self._state = new_state
        self._last_state_change = time.time()
        logger.info(f"[Scheduler] {old.value} -> {new_state.value}")

    def _run(self) -> None:
        """Main scheduler loop (thread target)."""
        try:
            while not self._stop_event.is_set():
                self._tick()
                self._stop_event.wait(self._poll_interval)
        except Exception as e:
            logger.error(f"[Scheduler] Crashed: {e}", exc_info=True)
            with self._lock:
                self._last_error = str(e)
                self._transition(SchedulerState.ERROR)
                self._running = False

    def _tick(self) -> None:
        """Single tick of the state machine."""
        with self._lock:
            current = self._state

        if current == SchedulerState.WAITING_COMPLETION:
            if self._check_wait_timeout():
                return
            if self._all_queues_empty_and_has_work():
                with self._lock:
                    self._transition(SchedulerState.RETRYING_FAILED)

        elif current == SchedulerState.RETRYING_FAILED:
            self._do_retry_failed()

        elif current == SchedulerState.WAITING_RETRY_COMPLETION:
            if self._check_wait_timeout():
                return
            if self._all_queues_empty_and_has_work():
                with self._lock:
                    self._transition(SchedulerState.CLONING_DB)

        elif current == SchedulerState.CLONING_DB:
            self._do_clone_db()

        elif current == SchedulerState.STARTING_PRODUCER:
            self._do_start_producer()

    def _all_queues_empty_and_has_work(self) -> bool:
        """
        Check if all active queues are empty AND total_games > 0.
        Uses a single Redis pipeline call for atomicity.
        """
        stats = self._redis_queue.get_all_queue_stats()
        total_games = stats["total_games"]

        if total_games == 0:
            return False

        return (
            stats["work_queue_length"] == 0
            and stats["processing_queue_length"] == 0
            and stats["result_queue_length"] == 0
            and stats["saving_queue_length"] == 0
        )

    def _check_wait_timeout(self) -> bool:
        """Check if we've been waiting too long. Returns True if timed out."""
        with self._lock:
            if self._last_state_change is None:
                return False
            elapsed = time.time() - self._last_state_change
            if elapsed > self._max_wait_time:
                self._last_error = (
                    f"Timeout: stuck in {self._state.value} for "
                    f"{elapsed / 3600:.1f} hours (max: {self._max_wait_time / 3600:.0f}h)"
                )
                self._transition(SchedulerState.ERROR)
                self._running = False
                return True
        return False

    def _do_retry_failed(self) -> None:
        """Retry failed and processing jobs, then transition."""
        logger.info("[Scheduler] Retrying failed and processing jobs")
        try:
            self._redis_queue.push_failed_jobs()
            self._redis_queue.push_processing_jobs()
        except Exception as e:
            logger.error(f"[Scheduler] Retry failed: {e}", exc_info=True)
            with self._lock:
                self._last_error = f"Retry failed: {e}"
                self._transition(SchedulerState.ERROR)
                self._running = False
            return

        # Check if anything was actually retried
        if self._all_queues_empty_and_has_work():
            # Nothing was retried, skip straight to cloning
            with self._lock:
                self._transition(SchedulerState.CLONING_DB)
        else:
            with self._lock:
                self._transition(SchedulerState.WAITING_RETRY_COMPLETION)

    def _do_clone_db(self) -> None:
        """Clone the database using TEMPLATE approach with Redis lock."""
        logger.info("[Scheduler] Starting database clone")
        try:
            self._clone_database()
            with self._lock:
                self._transition(SchedulerState.STARTING_PRODUCER)
        except Exception as e:
            logger.error(f"[Scheduler] DB clone failed: {e}", exc_info=True)
            with self._lock:
                self._last_error = f"DB clone failed: {e}"
                self._transition(SchedulerState.ERROR)
                self._running = False

    def _do_start_producer(self) -> None:
        """Reset Redis and start a new producer."""
        logger.info("[Scheduler] Resetting Redis and starting producer")
        try:
            # Reset Redis queues and stats
            from ..cli import reset_redis
            reset_redis.reset_redis(confirm=False)

            # Start producer
            success, result = start_producer(
                self._redis_queue,
                self._producer_mode,
                self._producer_sample_count if self._producer_mode == "test" else None,
            )
            if not success:
                raise RuntimeError(result.get("error", "Unknown error starting producer"))

            logger.info(f"[Scheduler] Producer started: {result}")
            with self._lock:
                self._cycle_count += 1
                self._transition(SchedulerState.WAITING_COMPLETION)

        except Exception as e:
            logger.error(f"[Scheduler] Producer start failed: {e}", exc_info=True)
            with self._lock:
                self._last_error = f"Producer start failed: {e}"
                self._transition(SchedulerState.ERROR)
                self._running = False

    def _verify_pg_tools(self) -> None:
        """Verify pg_dump and psql are available on PATH."""
        for tool in ("pg_dump", "psql"):
            try:
                result = subprocess.run(
                    [tool, "--version"],
                    capture_output=True, text=True, timeout=10
                )
                if result.returncode != 0:
                    raise RuntimeError(f"{tool} --version failed: {result.stderr}")
                logger.info(f"[Scheduler] Found {tool}: {result.stdout.strip()}")
            except FileNotFoundError:
                raise RuntimeError(
                    f"{tool} not found on PATH. "
                    "Install postgresql-client in the Docker image."
                )

    def _clone_database(self) -> None:
        """Clone the database using pg_dump piped to psql."""
        clone_name = self._clone_db_name
        if not clone_name:
            logger.info("[Scheduler] No clone_db_name configured, skipping clone")
            return

        # Check embedding lock - wait if embedding is in progress
        try:
            embedding_lock = self._redis_queue.client.get(EMBEDDING_LOCK_KEY)
            if embedding_lock:
                raise RuntimeError(
                    "Embedding is in progress (lock:embedding exists). "
                    "Cannot clone database during embedding."
                )
        except RuntimeError:
            raise
        except Exception as e:
            # Redis ACL may not have permission for lock:embedding yet
            # (embedding system not deployed). Log and continue.
            logger.warning(f"[Scheduler] Could not check embedding lock: {e}")

        # Acquire clone lock in Redis (best-effort if ACL lacks permission)
        clone_lock_acquired = False
        try:
            acquired = self._redis_queue.client.set(
                CLONE_LOCK_KEY, "scheduler", nx=True, ex=CLONE_LOCK_TTL
            )
            if not acquired:
                raise RuntimeError(
                    "Failed to acquire clone lock (lock:db_clone). "
                    "Another clone or embedding operation may be in progress."
                )
            clone_lock_acquired = True
        except RuntimeError:
            raise
        except Exception as e:
            logger.warning(f"[Scheduler] Could not acquire clone lock in Redis: {e}")

        try:
            source_db_name = self._db_name
            maintenance_url = (
                f"postgresql://{self._db_user}:{self._db_password}"
                f"@{self._db_host}:{self._db_port}/postgres"
            )

            # Phase 1: Drop and recreate empty clone DB
            engine = create_engine(maintenance_url, isolation_level="AUTOCOMMIT")
            try:
                with engine.connect() as conn:
                    # Terminate connections to clone DB only (NOT source)
                    conn.execute(text(
                        "SELECT pg_terminate_backend(pid) "
                        "FROM pg_stat_activity "
                        "WHERE datname = :db_name AND pid <> pg_backend_pid()"
                    ), {"db_name": clone_name})

                    conn.execute(text(f"DROP DATABASE IF EXISTS {clone_name}"))
                    logger.info(f"[Scheduler] Dropped existing clone DB '{clone_name}' (if any)")

                    conn.execute(text(f"CREATE DATABASE {clone_name}"))
                    logger.info(f"[Scheduler] Created empty clone DB '{clone_name}'")
            finally:
                engine.dispose()

            # Phase 2: pg_dump source | psql clone
            env = os.environ.copy()
            env["PGPASSWORD"] = self._db_password

            pg_dump_cmd = [
                "pg_dump",
                "-h", self._db_host,
                "-p", str(self._db_port),
                "-U", self._db_user,
                "-d", source_db_name,
                "--no-owner",
                "--no-privileges",
                "--no-tablespaces",
            ]

            # Filter out problematic SET commands that may not be recognized
            filter_cmd = [
                "grep",
                "-v",
                "-E",
                "^SET (transaction_timeout|idle_in_transaction_session_timeout)",
            ]

            psql_cmd = [
                "psql",
                "-h", self._db_host,
                "-p", str(self._db_port),
                "-U", self._db_user,
                "-d", clone_name,
                "-v", "ON_ERROR_STOP=1",
                "--quiet",
            ]

            logger.info(
                f"[Scheduler] Starting pg_dump '{source_db_name}' | grep -v | psql '{clone_name}'"
            )

            dump_proc = subprocess.Popen(
                pg_dump_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
            )

            filter_proc = subprocess.Popen(
                filter_cmd,
                stdin=dump_proc.stdout,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            restore_proc = subprocess.Popen(
                psql_cmd,
                stdin=filter_proc.stdout,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
            )

            # Allow proper SIGPIPE propagation
            if dump_proc.stdout:
                dump_proc.stdout.close()
            if filter_proc.stdout:
                filter_proc.stdout.close()

            try:
                _, restore_stderr = restore_proc.communicate(timeout=1800)
                filter_proc.wait(timeout=60)
                dump_proc.wait(timeout=60)
            except subprocess.TimeoutExpired:
                dump_proc.kill()
                filter_proc.kill()
                restore_proc.kill()
                raise RuntimeError("pg_dump|grep|psql pipeline timed out after 30 minutes")

            if dump_proc.returncode != 0:
                dump_stderr = (
                    dump_proc.stderr.read().decode("utf-8", errors="replace")
                    if dump_proc.stderr else "unknown error"
                )
                raise RuntimeError(
                    f"pg_dump failed (rc={dump_proc.returncode}): {dump_stderr}"
                )

            if filter_proc.returncode not in (0, 1):
                # grep returns 1 if no lines matched, which is OK
                filter_stderr = (
                    filter_proc.stderr.read().decode("utf-8", errors="replace")
                    if filter_proc.stderr else "unknown error"
                )
                raise RuntimeError(
                    f"grep filter failed (rc={filter_proc.returncode}): {filter_stderr}"
                )

            if restore_proc.returncode != 0:
                stderr_text = restore_stderr.decode("utf-8", errors="replace")
                raise RuntimeError(
                    f"psql restore failed (rc={restore_proc.returncode}): {stderr_text}"
                )

            logger.info(
                f"[Scheduler] Cloned '{source_db_name}' -> '{clone_name}' via pg_dump|psql"
            )
        finally:
            # Release clone lock if we acquired it
            if clone_lock_acquired:
                try:
                    self._redis_queue.client.delete(CLONE_LOCK_KEY)
                    logger.info("[Scheduler] Released clone lock")
                except Exception as e:
                    logger.warning(f"[Scheduler] Could not release clone lock: {e}")
