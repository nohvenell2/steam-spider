"""Reset both Redis and PostgreSQL CLI utility."""

import sys
from . import reset_redis, reset_db


def reset_all(confirm: bool = True) -> int:
    """
    Reset both Redis and PostgreSQL.

    Args:
        confirm: Ask for confirmation (default: True)

    Returns:
        Exit code
    """
    print("=" * 60)
    print("Full System Reset Utility")
    print("=" * 60)

    if confirm:
        print("\n⚠ WARNING: This will delete ALL data from Redis AND PostgreSQL!")
        response = input("Are you absolutely sure? (yes/no): ").strip().lower()
        if response not in ['yes', 'y']:
            print("\n✗ Cancelled by user")
            return 1

    # Reset Redis
    print("\n" + "=" * 60)
    print("Resetting Redis...")
    print("=" * 60)
    redis_result = reset_redis.reset_redis(confirm=False)
    if redis_result != 0:
        print("\n❌ Redis reset failed, aborting")
        return 1

    # Reset PostgreSQL
    print("\n" + "=" * 60)
    print("Resetting PostgreSQL...")
    print("=" * 60)
    db_result = reset_db.reset_database(confirm=False)
    if db_result != 0:
        print("\n❌ Database reset failed")
        return 1

    print("\n" + "=" * 60)
    print("✓ Full system reset completed successfully!")
    print("=" * 60)
    return 0


def main() -> int:
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Reset both Redis and PostgreSQL")
    parser.add_argument(
        "-f", "--force",
        action="store_true",
        help="Force reset without confirmation"
    )

    args = parser.parse_args()
    return reset_all(confirm=not args.force)


if __name__ == "__main__":
    sys.exit(main())
