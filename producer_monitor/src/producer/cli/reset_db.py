"""Reset PostgreSQL database CLI utility."""

import sys
from typing import Dict, Any
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
import os

load_dotenv()


def get_database_url() -> str:
    """Get PostgreSQL connection URL from environment."""
    user = os.getenv("POSTGRES_USER", "steam_user")
    password = os.getenv("POSTGRES_PASSWORD", "steam_password")
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    db = os.getenv("POSTGRES_DB", "steam_games")

    return f"postgresql://{user}:{password}@{host}:{port}/{db}"


def reset_database(confirm: bool = True) -> int:
    """
    Truncate all PostgreSQL tables.

    Args:
        confirm: Ask for confirmation (default: True)

    Returns:
        Exit code
    """
    print("=" * 60)
    print("PostgreSQL Reset Utility")
    print("=" * 60)

    # Tables in FK dependency order (delete children first)
    tables = ["reviews", "tags", "genres", "basic_info"]

    try:
        engine = create_engine(get_database_url())

        # Get current counts
        with engine.connect() as conn:
            print("\nCurrent Table Counts:")
            counts = {}
            total = 0
            for table in tables:
                result = conn.execute(text(f"SELECT COUNT(*) FROM {table}"))
                count = result.scalar()
                counts[table] = count
                total += count
                print(f"  {table}: {count} rows")

            if total == 0:
                print("\n✓ Database is already empty!")
                return 0

            # Confirm
            if confirm:
                print(f"\n⚠ WARNING: This will delete all data ({total} rows)!")
                response = input("Continue? (yes/no): ").strip().lower()
                if response not in ['yes', 'y']:
                    print("\n✗ Cancelled by user")
                    return 1

            # Truncate tables
            print("\nTruncating tables...")
            conn.execute(text("BEGIN"))
            try:
                for table in tables:
                    conn.execute(text(f"TRUNCATE TABLE {table} CASCADE"))
                    print(f"  ✓ Truncated {table}")
                conn.execute(text("COMMIT"))
            except Exception:
                conn.execute(text("ROLLBACK"))
                raise

            print("\n✓ All tables truncated successfully!")
            return 0

    except Exception as e:
        print(f"\n❌ Error: {e}")
        return 1


def main() -> int:
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Truncate all PostgreSQL tables")
    parser.add_argument(
        "-f", "--force",
        action="store_true",
        help="Force truncate without confirmation"
    )

    args = parser.parse_args()
    return reset_database(confirm=not args.force)


if __name__ == "__main__":
    sys.exit(main())
