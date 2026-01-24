"""Recover processing queue CLI utility."""

import sys
from ..queue import RedisQueue


def recover_processing(confirm: bool = True) -> int:
    """
    Move jobs from processing queue back to work queue.

    Args:
        confirm: Ask for confirmation (default: True)

    Returns:
        Exit code
    """
    print("=" * 60)
    print("Processing Queue Recovery Utility")
    print("=" * 60)

    try:
        with RedisQueue() as queue:
            processing_count = queue.get_processing_queue_length()

            print(f"\nProcessing Queue: {processing_count} jobs")

            if processing_count == 0:
                print("\n✓ Processing queue is empty, nothing to recover")
                return 0

            # Confirm
            if confirm:
                print(f"\n⚠ This will move {processing_count} jobs to work queue")
                response = input("Continue? (yes/no): ").strip().lower()
                if response not in ['yes', 'y']:
                    print("\n✗ Cancelled by user")
                    return 1

            # Recover
            print("\nRecovering jobs...")
            recovered = queue.recover_processing_queue()
            print(f"\n✓ Recovered {recovered} jobs to work queue!")
            return 0

    except Exception as e:
        print(f"\n❌ Error: {e}")
        return 1


def main() -> int:
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Recover processing queue")
    parser.add_argument(
        "-f", "--force",
        action="store_true",
        help="Force recovery without confirmation"
    )

    args = parser.parse_args()
    return recover_processing(confirm=not args.force)


if __name__ == "__main__":
    sys.exit(main())
