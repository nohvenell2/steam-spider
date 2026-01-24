"""Database initialization script - Creates all tables in PostgreSQL"""

from src.db.connection import init_db, get_engine
from sqlalchemy import text

def main():
    print("=" * 60)
    print("Steam-Spider Database Initialization")
    print("=" * 60)
    print()

    try:
        # Initialize database and create tables
        print("📦 Connecting to PostgreSQL...")
        init_db()

        print("✓ Connected successfully")
        print()

        # Verify tables were created
        print("🔍 Verifying table creation...")
        engine = get_engine()

        with engine.connect() as conn:
            result = conn.execute(
                text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema='public' ORDER BY table_name"
                )
            )
            tables = [row[0] for row in result.fetchall()]

        if tables:
            print(f"✓ Created {len(tables)} tables:")
            for table in tables:
                print(f"  - {table}")
        else:
            print("⚠ No tables found!")

        print()
        print("=" * 60)
        print("✓ Database initialization completed successfully!")
        print("=" * 60)

    except Exception as e:
        print()
        print("=" * 60)
        print("✗ Error during initialization:")
        print(f"  {e}")
        print("=" * 60)
        print()
        print("Troubleshooting:")
        print("1. Make sure Docker containers are running:")
        print("   docker-compose up -d")
        print()
        print("2. Check PostgreSQL connection:")
        print("   docker ps")
        print()
        exit(1)

if __name__ == "__main__":
    main()