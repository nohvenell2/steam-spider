import os
import logging
import redis
from typing import Dict, Any, Set, Optional
from dotenv import load_dotenv

load_dotenv()
LOCK_KEY = "lock:producer"
logger = logging.getLogger(__name__)

def cleanup_lock():
    """
    Force release the producer lock in Redis.
    Must be called upon any exit (success or error).
    """
    try:
        # 환경변수에서 설정 로드 (없으면 기본값)
        redis_host = os.getenv("REDIS_HOST", "localhost")
        redis_port = int(os.getenv("REDIS_PORT", 6379))
        redis_username = os.getenv("REDIS_ID_PRODUCER_MONITOR", None)
        redis_password = os.getenv("REDIS_PW_PRODUCER_MONITOR", None)

        r = redis.Redis(
            host=redis_host, 
            port=redis_port, 
            username=redis_username, 
            password=redis_password, 
            db=0, # 기본 DB 사용
            socket_timeout=5
        )
        
        # 락 삭제
        r.delete(LOCK_KEY)
        logger.info(f"🔒 Lock '{LOCK_KEY}' released successfully.")
        
    except Exception as e:
        logger.error(f"Failed to release lock: {e}")
if __name__ == "__main__":
    cleanup_lock()