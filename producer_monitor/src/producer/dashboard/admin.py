"""Admin operations for dashboard (reset and producer control)."""

import os
import sys
import json
import time
import subprocess
import logging
from typing import Dict, Any, Optional, Tuple

from ..cli import reset_redis, reset_db, reset_all
from ..queue import RedisQueue

logger = logging.getLogger(__name__)

# Constants
REQUIRED_CONFIRMATION_PHRASE = "DELETE ALL DATA"
PRODUCER_LOCK_KEY = "lock:producer"
PRODUCER_START_TIME_KEY = "stats:producer_start_time"


# ========================================
# Reset Operations
# ========================================

def execute_reset(action: str) -> Tuple[bool, Dict[str, Any]]:
    """
    Execute reset operation.

    Args:
        action: "redis", "database", or "all"

    Returns:
        (success, data) tuple
    """
    try:
        # Capture stats before reset
        stats_before = {}

        if action in ["redis", "all"]:
            with RedisQueue() as queue:
                stats_before.update(queue.get_all_queue_stats())

        # Execute reset
        if action == "redis":
            result = reset_redis.reset_redis(confirm=False)
            # Clear producer start time
            with RedisQueue() as queue:
                queue.client.delete(PRODUCER_START_TIME_KEY)
            message = "Redis queues cleared successfully"
        elif action == "database":
            result = reset_db.reset_database(confirm=False)
            message = "PostgreSQL tables truncated successfully"
        elif action == "all":
            result = reset_all.reset_all(confirm=False)
            # Clear producer start time
            with RedisQueue() as queue:
                queue.client.delete(PRODUCER_START_TIME_KEY)
            message = "Full system reset completed successfully"
        else:
            return False, {"error": "Invalid action"}

        if result == 0:
            return True, {
                "message": message,
                "stats_before": stats_before
            }
        else:
            return False, {"error": "Reset operation failed"}

    except Exception as e:
        logger.error(f"Reset failed: {e}", exc_info=True)
        return False, {"error": str(e)}


# ========================================
# Producer Lock Management
# ========================================

def get_producer_status(redis_queue: RedisQueue) -> Dict[str, Any]:
    """
    Get current producer execution status.

    Args:
        redis_queue: RedisQueue instance

    Returns:
        Status dictionary
    """
    lock_data = validate_and_clean_lock(redis_queue)

    if not lock_data:
        return {"is_running": False}

    ttl = redis_queue.client.ttl(PRODUCER_LOCK_KEY)
    lock_expires_at = time.time() + ttl if ttl > 0 else None

    return {
        "is_running": True,
        "pid": lock_data.get("pid"),
        "mode": lock_data.get("mode"),
        "sample_count": lock_data.get("sample_count"),
        "started_at": lock_data.get("started_at"),
        "lock_expires_at": lock_expires_at
    }


def validate_and_clean_lock(redis_queue: RedisQueue) -> Optional[Dict[str, Any]]:
    """
    Validate existing lock and clean up if stale.

    Args:
        redis_queue: RedisQueue instance

    Returns:
        Lock metadata if valid, None otherwise
    """
    lock_value = redis_queue.client.get(PRODUCER_LOCK_KEY)
    if not lock_value:
        return None

    try:
        lock_data = json.loads(lock_value)
        pid = lock_data.get("pid")

        if pid is None:
            # Lock without PID (race condition or startup delay)
            if time.time() - lock_data.get("started_at", 0) > 60:
                redis_queue.client.delete(PRODUCER_LOCK_KEY)
                logger.warning("Cleaned up stale lock without PID")
                return None
            return lock_data

        # Verify process is running
        if not is_process_running(pid):
            redis_queue.client.delete(PRODUCER_LOCK_KEY)
            logger.warning(f"Cleaned up stale lock for dead process {pid}")
            return None

        return lock_data

    except (json.JSONDecodeError, KeyError, TypeError) as e:
        # Corrupted lock data
        redis_queue.client.delete(PRODUCER_LOCK_KEY)
        logger.error(f"Cleaned up corrupted lock: {e}")
        return None


def is_process_running(pid: int) -> bool:
    """
    Check if process with PID is running.

    Args:
        pid: Process ID

    Returns:
        True if running, False otherwise
    """
    try:
        # Send signal 0 (null signal) to check existence
        # Works on both Windows and Unix
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


def acquire_producer_lock(
    redis_queue: RedisQueue,
    mode: str,
    sample_count: Optional[int] = None
) -> bool:
    """
    Attempt to acquire producer execution lock.

    Args:
        redis_queue: RedisQueue instance
        mode: "production" or "test"
        sample_count: Sample count for test mode

    Returns:
        True if lock acquired, False otherwise
    """
    lock_ttl = int(os.getenv("PRODUCER_LOCK_TTL", "43200"))  # 12 hours default

    lock_data = {
        "pid": None,  # Will be updated after process starts
        "mode": mode,
        "sample_count": sample_count,
        "started_at": time.time(),
        "hostname": os.uname().nodename if hasattr(os, 'uname') else os.environ.get('COMPUTERNAME', 'unknown')
    }

    # SET NX (set if not exists) with TTL
    acquired = redis_queue.client.set(
        PRODUCER_LOCK_KEY,
        json.dumps(lock_data),
        nx=True,
        ex=lock_ttl
    )

    return bool(acquired)


def update_producer_lock_pid(redis_queue: RedisQueue, pid: int) -> None:
    """
    Update producer lock with process PID.

    Args:
        redis_queue: RedisQueue instance
        pid: Process ID
    """
    lock_ttl = int(os.getenv("PRODUCER_LOCK_TTL", "43200"))
    lock_value = redis_queue.client.get(PRODUCER_LOCK_KEY)
    if lock_value:
        lock_data = json.loads(lock_value)
        lock_data["pid"] = pid
        redis_queue.client.set(
            PRODUCER_LOCK_KEY,
            json.dumps(lock_data),
            ex=lock_ttl            
        )


# ========================================
# Producer Execution
# ========================================

def start_producer(
    redis_queue: RedisQueue,
    mode: str,
    sample_count: Optional[int] = None
) -> Tuple[bool, Dict[str, Any]]:
    """
    Start producer as background subprocess.

    Args:
        redis_queue: RedisQueue instance
        mode: "production" or "test"
        sample_count: Sample count for test mode

    Returns:
        (success, data) tuple
    """
    # Check if already running
    existing_lock = validate_and_clean_lock(redis_queue)
    if existing_lock:
        pid = existing_lock.get("pid")
        return False, {
            "error": f"Producer is already running (PID: {pid})"
        }

    # Acquire lock
    if not acquire_producer_lock(redis_queue, mode, sample_count):
        return False, {
            "error": "Failed to acquire lock. Another producer may be starting."
        }

    try:
        # Start subprocess
        pid = start_producer_subprocess(mode, sample_count)

        # Update lock with PID
        update_producer_lock_pid(redis_queue, pid)

        # Record producer start time
        redis_queue.client.set(PRODUCER_START_TIME_KEY, str(time.time()))

        message = f"Producer started in {mode} mode"
        if mode == "test":
            message += f" with {sample_count} samples"

        return True, {
            "message": message,
            "pid": pid,
            "mode": mode,
            "sample_count": sample_count
        }

    except Exception as e:
        # Release lock on failure
        redis_queue.client.delete(PRODUCER_LOCK_KEY)
        logger.error(f"Failed to start producer: {e}", exc_info=True)
        return False, {"error": str(e)}


def start_producer_subprocess(mode: str, sample_count: Optional[int] = None) -> int:
    """
    Start producer as detached subprocess.

    Args:
        mode: "production" or "test"
        sample_count: Sample count for test mode

    Returns:
        Process PID
    """
    python_exe = sys.executable

    # Get project root (where pyproject.toml is)
    project_root = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "..")
    )

    # Build command
    cmd = [python_exe, "-m", "src.producer.main"]

    if mode == "test" and sample_count:
        cmd.extend(["--sample", str(sample_count)])

    # Start detached process
    if sys.platform == "win32":
        # Windows: use DETACHED_PROCESS flag (don't use close_fds on Windows)
        NEW_PROCESS_GROUP = subprocess.CREATE_NEW_PROCESS_GROUP
        process = subprocess.Popen(
            cmd,
            cwd=project_root,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            creationflags=NEW_PROCESS_GROUP,
            shell=False
        )
    else:
        # Linux/Unix: start new session
        process = subprocess.Popen(
            cmd,
            cwd=project_root,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
            close_fds=True
        )

    logger.info(f"Started producer subprocess with PID {process.pid}")
    return process.pid


# ========================================
# Rate Limiting
# ========================================

def check_rate_limit(
    redis_queue: RedisQueue,
    action: str,
    limit: int,
    window: int
) -> bool:
    """
    Check if action is rate-limited.

    Args:
        redis_queue: RedisQueue instance
        action: Action identifier
        limit: Max requests per window
        window: Time window in seconds

    Returns:
        True if allowed, False if rate-limited
    """
    key = f"ratelimit:{action}"
    count = redis_queue.client.incr(key)

    if count == 1:
        redis_queue.client.expire(key, window)

    return count <= limit
