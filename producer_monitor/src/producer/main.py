"""Main Producer module for Steam-Spider."""

import sys
import os
import logging
from typing import Dict, Any, Set, Optional

# 로깅 설정 (시간 포함)
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)

from .api import fetch_all_apps, fetch_apps_sample
from .queue import RedisQueue

def run_producer(
    queue: RedisQueue,
    use_sample: bool = False,
    sample_count: int = 100,
    exclude_ids: Optional[Set[int]] = None,
    batch_size: int = 2000
) -> Dict[str, Any]:
    """
    Run the Producer workflow: Fetch Steam apps and push to Redis queue.
    """
    logger.info("=" * 40)
    logger.info("Steam-Spider Producer Started")
    logger.info("=" * 40)

    # Step 1: Fetch Steam apps
    logger.info("[Step 1/5] Fetching Steam apps from API...")
    if use_sample:
        apps = fetch_apps_sample(count=sample_count)
    else:
        apps = fetch_all_apps()

    total_fetched = len(apps)
    logger.info(f"✓ Fetched {total_fetched} apps from Steam API")

    # Step 2: Extract game IDs
    logger.info("[Step 2/5] Extracting game IDs...")
    all_ids = [app["appid"] for app in apps]
    logger.info(f"✓ Extracted {len(all_ids)} game IDs")

    # Step 3: Filter out excluded IDs
    logger.info("[Step 3/5] Filtering game IDs...")
    if exclude_ids:
        filtered_ids = [gid for gid in all_ids if gid not in exclude_ids]
        total_excluded = len(all_ids) - len(filtered_ids)
        logger.info(f"  Excluded {total_excluded} already processed IDs")
    else:
        filtered_ids = all_ids
        total_excluded = 0
        logger.info("  No exclusion filter applied")

    logger.info(f"✓ {len(filtered_ids)} game IDs ready for processing")

    # Step 4: Sort descending (newest games first)
    logger.info("[Step 4/5] Sorting game IDs (descending)...")
    sorted_ids = sorted(filtered_ids, reverse=True)
    logger.info(f"✓ Sorted {len(sorted_ids)} IDs")
    
    if sorted_ids:
        logger.info(f"  ID range: {sorted_ids[0]} (newest) -> {sorted_ids[-1]} (oldest)")

    # Step 5: Push to Redis queue
    logger.info("[Step 5/5] Pushing jobs to Redis queue...")
    queue_stats = {}
    total_pushed = 0

    if not sorted_ids:
        logger.warning("⚠ No jobs to push (all IDs were filtered out)")
    else:
        # Store total games for progress calculation
        total_pushed = queue.push_jobs(sorted_ids, batch_size=batch_size)
        queue_stats = queue.get_queue_stats()

    # Summary
    logger.info("-" * 40)
    logger.info("Producer Summary")
    logger.info("-" * 40)
    logger.info(f"Total fetched:  {total_fetched}")
    logger.info(f"Total excluded: {total_excluded}")
    logger.info(f"Total pushed:   {total_pushed}")
    
    if queue_stats:
        logger.info("Redis Queue Status:")
        logger.info(f"  Work queue:   {queue_stats.get('work_queue_length', 0)} jobs")
        logger.info(f"  Result queue: {queue_stats.get('result_queue_length', 0)} results")
    
    logger.info("=" * 40)

    return {
        "total_fetched": total_fetched,
        "total_excluded": total_excluded,
        "total_pushed": total_pushed,
        "queue_stats": queue_stats
    }

def main() -> int:
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Steam-Spider Producer")
    parser.add_argument("--sample", type=int, help="Run in sample mode with N apps")
    parser.add_argument("--batch-size", type=int, default=2000, help="Batch size for Redis")

    args = parser.parse_args()

    # Record producer start time
    try:
        with RedisQueue() as queue:
            try:
                # todo lock 을 거는 코드가 위치해야하는 곳
                queue.set_producer_start_time()
            except Exception as e:
                logger.warning(f"Failed to record start time: {e}")
            try:
                if args.sample:
                    logger.info(f"Starting SAMPLE mode ({args.sample} apps)")
                    run_producer(
                        queue=queue,
                        use_sample=True,
                        sample_count=args.sample,
                        batch_size=args.batch_size
                    )
                else:
                    logger.info("Starting FULL mode")
                    run_producer(queue=queue, batch_size=args.batch_size)

                return 0

            except KeyboardInterrupt:
                logger.warning("⚠ Interrupted by user")
                return 0
            except Exception as e:
                logger.error(f"❌ Critical Error: {e}", exc_info=True)
                return 1
            finally:
                # release lock
                queue.release_producer_lock()
    except Exception as e:
        logger.error(f"❌ Failed to connect to Redis: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())