"""
Steam API Client - Fetch all Steam app data from Steam API.

This package provides functionality to fetch the complete list of Steam apps
from the Steam Web API.
"""

from .steam_api import fetch_all_apps, fetch_apps_sample
from .exceptions import SteamAPIError, APIKeyError, NetworkError

__version__ = "0.1.0"

__all__ = [
    "fetch_all_apps",
    "fetch_apps_sample",
    "SteamAPIError",
    "APIKeyError",
    "NetworkError"
]
