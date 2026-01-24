"""Configuration management for DB Writer"""

import os
from typing import Optional
from dotenv import load_dotenv

from dbwriter.exceptions import ConfigurationError


class Config:
    """
    Configuration management with environment variables.

    Loads configuration from .env file and provides typed access.
    """

    def __init__(self, env_file: str = ".env"):
        """
        Initialize configuration.

        Args:
            env_file: Path to .env file (default: ".env")
        """
        # Load environment variables from .env file
        load_dotenv(env_file, override=False)

        # Redis Configuration
        self.REDIS_HOST = self._get_env("REDIS_HOST", "localhost")
        self.REDIS_PORT = self._get_env_int("REDIS_PORT", 6379)
        self.REDIS_DB = self._get_env_int("REDIS_DB", 0)
        self.REDIS_ID_DBWRITER = self._get_env("REDIS_ID_DBWRITER", "dbwriter_id")
        self.REDIS_PW_DBWRITER = self._get_env("REDIS_PW_DBWRITER", "dbwriter_password")

        # Redis TLS/SSL Configuration
        self.REDIS_SSL_ENABLED = self._get_env_bool("REDIS_SSL_ENABLED", False)
        self.REDIS_SSL_CA_CERT = self._get_env("REDIS_SSL_CA_CERT", "")
        self.REDIS_SSL_CERT = self._get_env("REDIS_SSL_CERT", "")
        self.REDIS_SSL_KEY = self._get_env("REDIS_SSL_KEY", "")
        self.REDIS_SSL_CHECK_HOSTNAME = self._get_env_bool("REDIS_SSL_CHECK_HOSTNAME", False)


        # PostgreSQL Configuration
        self.POSTGRES_USER = self._get_env("POSTGRES_USER", "steam_user")
        self.POSTGRES_PASSWORD = self._get_env("POSTGRES_PASSWORD", "steam_password")
        self.POSTGRES_HOST = self._get_env("POSTGRES_HOST", "localhost")
        self.POSTGRES_PORT = self._get_env_int("POSTGRES_PORT", 5432)
        self.POSTGRES_DB = self._get_env("POSTGRES_DB", "steam_games")

        # Batch Processing Configuration
        self.BUFFER_SIZE = self._get_env_int("BUFFER_SIZE", 100)
        self.BUFFER_TIMEOUT = self._get_env_int("BUFFER_TIMEOUT", 10)

        # Error Handling Configuration
        self.MAX_DB_RETRIES = self._get_env_int("MAX_DB_RETRIES", 3)
        self.MAX_REDIS_RETRIES = self._get_env_int("MAX_REDIS_RETRIES", 5)
        self.RETRY_BASE_DELAY = self._get_env_float("RETRY_BASE_DELAY", 1.0)
        self.RETRY_MAX_DELAY = self._get_env_float("RETRY_MAX_DELAY", 60.0)

        # Logging Configuration
        self.LOG_LEVEL = self._get_env("LOG_LEVEL", "INFO").upper()
        self.DB_ECHO = self._get_env_bool("DB_ECHO", False)

        # Validate configuration
        self._validate()

    def _get_env(self, key: str, default: str) -> str:
        """Get string environment variable."""
        return os.getenv(key, default)

    def _get_env_int(self, key: str, default: int) -> int:
        """Get integer environment variable."""
        value = os.getenv(key)
        if value is None:
            return default
        try:
            return int(value)
        except ValueError:
            raise ConfigurationError(f"Invalid integer value for {key}: {value}")

    def _get_env_float(self, key: str, default: float) -> float:
        """Get float environment variable."""
        value = os.getenv(key)
        if value is None:
            return default
        try:
            return float(value)
        except ValueError:
            raise ConfigurationError(f"Invalid float value for {key}: {value}")

    def _get_env_bool(self, key: str, default: bool) -> bool:
        """Get boolean environment variable."""
        value = os.getenv(key)
        if value is None:
            return default
        return value.lower() in ("true", "1", "yes", "on")

    def _validate(self):
        """Validate configuration values."""
        # Validate buffer size
        if self.BUFFER_SIZE <= 0:
            raise ConfigurationError(f"BUFFER_SIZE must be positive: {self.BUFFER_SIZE}")

        # Validate buffer timeout
        if self.BUFFER_TIMEOUT <= 0:
            raise ConfigurationError(f"BUFFER_TIMEOUT must be positive: {self.BUFFER_TIMEOUT}")

        # Validate retry configuration
        if self.MAX_DB_RETRIES < 0:
            raise ConfigurationError(f"MAX_DB_RETRIES must be non-negative: {self.MAX_DB_RETRIES}")

        if self.RETRY_BASE_DELAY <= 0:
            raise ConfigurationError(f"RETRY_BASE_DELAY must be positive: {self.RETRY_BASE_DELAY}")

        if self.RETRY_MAX_DELAY < self.RETRY_BASE_DELAY:
            raise ConfigurationError(
                f"RETRY_MAX_DELAY ({self.RETRY_MAX_DELAY}) must be >= RETRY_BASE_DELAY ({self.RETRY_BASE_DELAY})"
            )

        # Validate log level
        valid_log_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if self.LOG_LEVEL not in valid_log_levels:
            raise ConfigurationError(
                f"Invalid LOG_LEVEL: {self.LOG_LEVEL}. Must be one of {valid_log_levels}"
            )

    def get_database_url(self) -> str:
        """
        Get PostgreSQL connection URL.

        Returns:
            PostgreSQL connection URL string
        """
        return f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    def __repr__(self):
        """String representation (without sensitive data)."""
        return (
            f"Config("
            f"REDIS_HOST={self.REDIS_HOST}, "
            f"REDIS_PORT={self.REDIS_PORT}, "
            f"POSTGRES_HOST={self.POSTGRES_HOST}, "
            f"POSTGRES_PORT={self.POSTGRES_PORT}, "
            f"BUFFER_SIZE={self.BUFFER_SIZE}, "
            f"BUFFER_TIMEOUT={self.BUFFER_TIMEOUT})"
        )
