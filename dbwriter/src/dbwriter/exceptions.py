"""Custom exceptions for DB Writer"""


class DBWriterException(Exception):
    """Base exception for DB Writer module"""
    pass


class DatabaseConnectionError(DBWriterException):
    """Raised when database connection fails"""
    pass


class RedisConnectionError(DBWriterException):
    """Raised when Redis connection fails"""
    pass


class ConfigurationError(DBWriterException):
    """Raised when configuration is invalid"""
    pass


class DataValidationError(DBWriterException):
    """Raised when game data validation fails"""
    pass
