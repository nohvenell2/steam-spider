"""Reset Redis queues CLI utility."""

import sys
from typing import Any

from ..queue import RedisQueue


def reset_redis(confirm: bool = True) -> int:
    """
    Clear all Redis queues.

    Args:
        confirm: Ask for confirmation (default: True)

    Returns:
        Exit code
    """
    print("=" * 60)
    print("Redis Reset Utility")
    print("=" * 60)

    try:
        with RedisQueue() as queue:
            # Show current stats
            stats = queue.get_all_queue_stats()
            print("\nCurrent Redis Status:")
            print(f"  Work Queue:       {stats['work_queue_length']} jobs")
            print(f"  Result Queue:     {stats['result_queue_length']} results")
            print(f"  Processing Queue: {stats['processing_queue_length']} jobs")
            print(f"  Saving Queue:     {stats['saving_queue_length']} jobs")
            print(f"  Failed Crawl:     {stats['crawling_failed_queue_length']} jobs")
            print(f"  Failed Save:      {stats['saving_failed_queue_length']} jobs")
            print(f"  Producer Start:   {stats['producer_start_time']}")
            print(f"  Producer Lock:    {stats['producer_lock']}")
            print(f"  Total Games:      {stats['total_games']}")

            # Confirm
            if confirm:
                print(f"\n⚠ WARNING: This will delete all Redis data.")
                response = input("Continue? (yes/no): ").strip().lower()
                if response not in ['yes', 'y']:
                    print("\n✗ Cancelled by user")
                    return 1

            # Clear all
            print("\nClearing Redis...")
            queue.clear_all()
            print("\n✓ All Redis queues cleared successfully!")
            return 0

    except Exception as e:
        print(f"\n❌ Error: {e}")
        return 1


def main() -> int:
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Clear all Redis queues")
    parser.add_argument(
        "-f", "--force",
        action="store_true",
        help="Force clear without confirmation"
    )

    args = parser.parse_args()
    return reset_redis(confirm=not args.force)


if __name__ == "__main__":
    sys.exit(main())
