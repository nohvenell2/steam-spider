"""Dashboard configuration management."""

import os
from typing import Optional
from dotenv import load_dotenv

load_dotenv()


class DashboardConfig:
    """Dashboard configuration with validation."""

    def __init__(self) -> None:
        """Initialize configuration from environment variables."""
        # Redis configuration (reuse Producer's Redis)
        self.redis_host = self._get_env("REDIS_HOST", "localhost")
        self.redis_port = self._get_env_int("REDIS_PORT", 6379)
        self.redis_db = self._get_env_int("REDIS_DB", 0)
        self.redis_id_producer_monitor = self._get_env("REDIS_ID_PRODUCER_MONITOR", "producer_monitor_id")
        self.redis_pw_producer_monitor = self._get_env("REDIS_PW_PRODUCER_MONITOR", "producer_monitor_password")

        # PostgreSQL configuration
        self.postgres_user = self._get_env("POSTGRES_USER", "steam_user")
        self.postgres_password = self._get_env("POSTGRES_PASSWORD", "steam_password")
        self.postgres_host = self._get_env("POSTGRES_HOST", "localhost")
        self.postgres_port = self._get_env_int("POSTGRES_PORT", 5432)
        self.postgres_db = self._get_env("POSTGRES_DB", "steam_games")

        # Dashboard configuration
        self.dashboard_host = self._get_env("DASHBOARD_HOST", "localhost")
        self.dashboard_port = self._get_env_int("DASHBOARD_PORT", 8080)
        self.refresh_interval = self._get_env_int("REFRESH_INTERVAL", 2)
        self.refresh_interval_long = self._get_env_int("REFRESH_INTERVAL_LONG", 30)

        # Logging
        self.log_level = self._get_env("LOG_LEVEL", "INFO")

        # Rate limiting
        self.rate_limit_reset_count = self._get_env_int("RATE_LIMIT_RESET_COUNT", 999)
        self.rate_limit_reset_window = self._get_env_int("RATE_LIMIT_RESET_WINDOW", 60)
        self.rate_limit_producer_count = self._get_env_int("RATE_LIMIT_PRODUCER_COUNT", 999)
        self.rate_limit_producer_window = self._get_env_int("RATE_LIMIT_PRODUCER_WINDOW", 60)

        self._validate()

    def _get_env(self, key: str, default: Optional[str] = None) -> str:
        """
        Get environment variable.

        Args:
            key: Environment variable name
            default: Default value if not set

        Returns:
            Environment variable value

        Raises:
            ValueError: If environment variable not set and no default provided
        """
        value = os.getenv(key, default)
        if value is None:
            raise ValueError(f"Environment variable {key} not set")
        return value

    def _get_env_int(self, key: str, default: int) -> int:
        """
        Get integer environment variable.

        Args:
            key: Environment variable name
            default: Default value if not set

        Returns:
            Environment variable value as integer

        Raises:
            ValueError: If value cannot be converted to integer
        """
        value = os.getenv(key, str(default))
        try:
            return int(value)
        except ValueError:
            raise ValueError(f"Invalid integer value for {key}: {value}")

    def _validate(self) -> None:
        """
        Validate configuration.

        Raises:
            ValueError: If configuration is invalid
        """
        if self.refresh_interval < 1:
            raise ValueError("REFRESH_INTERVAL must be >= 1")
        if self.dashboard_port < 1 or self.dashboard_port > 65535:
            raise ValueError("DASHBOARD_PORT must be 1-65535")

    def get_database_url(self) -> str:
        """
        Get PostgreSQL connection URL.

        Returns:
            PostgreSQL connection string for SQLAlchemy
        """
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )
