"""Custom exceptions for Steam IDs fetcher."""


class SteamAPIError(Exception):
    """Base exception for Steam API errors."""
    pass


class APIKeyError(SteamAPIError):
    """Raised when Steam API key is missing or invalid."""
    pass


class NetworkError(SteamAPIError):
    """Raised when network request fails."""
    pass
