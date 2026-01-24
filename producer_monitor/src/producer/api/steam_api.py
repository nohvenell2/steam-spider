"""Fetch all Steam game IDs from Steam API."""

import os
import requests
import json
import random
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv

from .exceptions import SteamAPIError, APIKeyError, NetworkError


# Load environment variables from .env file
load_dotenv()

# API endpoint
STEAM_API_URL = "https://api.steampowered.com/IStoreService/GetAppList/v1/"


def _get_api_key() -> str:
    """
    Get Steam API key from environment variable.

    Returns:
        Steam API key string

    Raises:
        APIKeyError: If STEAM_API_KEY environment variable is not set
    """
    api_key = os.getenv("STEAM_API_KEY")
    if not api_key:
        raise APIKeyError(
            "STEAM_API_KEY environment variable is not set. "
            "Please set it in your .env file or as an environment variable."
        )
    return api_key


def fetch_all_apps(
    api_key: Optional[str] = None,
    max_results: int = 50000,
    include_games: bool = True,
    include_dlc: bool = False,
    include_software: bool = False,
    include_videos: bool = False,
    include_hardware: bool = False,
    timeout: int = 30
) -> List[Dict[str, Any]]:
    """
    Fetch all Steam app data from Steam API with pagination.

    This function automatically handles pagination to retrieve all available
    apps from the Steam store.

    Args:
        api_key: Steam Web API key (if None, reads from STEAM_API_KEY env var)
        max_results: Maximum results per request (default: 50000, max: 50000)
        include_games: Include game items (default: True)
        include_dlc: Include DLC items (default: False)
        include_software: Include software items (default: False)
        include_videos: Include video items (default: False)
        include_hardware: Include hardware items (default: False)
        timeout: Request timeout in seconds (default: 30)

    Returns:
        List of dictionaries containing app information:
            [
                {
                    "appid": 10,
                    "name": "Counter-Strike",
                    "last_modified": 1745368572,
                    "price_change_number": 31509480
                },
                {
                    "appid": 20,
                    "name": "Team Fortress Classic",
                    "last_modified": 1745368565,
                    "price_change_number": 31509480
                },
                ...
            ]

    Raises:
        APIKeyError: If API key is not provided and not in environment
        NetworkError: If API request fails
        ValueError: If max_results is invalid

    Examples:
        >>> # Using environment variable
        >>> apps = fetch_all_apps()
        >>> print(f"Total apps: {len(apps)}")

        >>> # Providing API key directly
        >>> apps = fetch_all_apps(api_key="YOUR_KEY_HERE")
    """
    # Get API key
    if api_key is None:
        api_key = _get_api_key()

    # Validate parameters
    if max_results <= 0 or max_results > 50000:
        raise ValueError(f"max_results must be between 1 and 50000, got {max_results}")

    all_apps = []
    last_appid = None
    page_count = 0

    print("Fetching Steam app list from API...")

    while True:
        page_count += 1

        # Build request parameters
        params = {
            "key": api_key,
            "max_results": max_results,
            "include_games": str(include_games).lower(),
            "include_dlc": str(include_dlc).lower(),
            "include_software": str(include_software).lower(),
            "include_videos": str(include_videos).lower(),
            "include_hardware": str(include_hardware).lower(),
        }

        # Add pagination parameter if not first request
        if last_appid is not None:
            params["last_appid"] = last_appid

        # Make API request
        try:
            response = requests.get(
                STEAM_API_URL,
                params=params,
                timeout=timeout
            )
        except requests.Timeout:
            raise NetworkError(f"Request timed out after {timeout}s")
        except requests.ConnectionError as e:
            raise NetworkError(f"Connection failed: {e}")
        except requests.RequestException as e:
            raise NetworkError(f"Request failed: {e}")

        # Check HTTP status
        if response.status_code == 403:
            raise APIKeyError("Invalid API key or access forbidden")
        elif response.status_code != 200:
            raise NetworkError(f"HTTP {response.status_code}: {response.text}")

        # Parse JSON response
        try:
            data = response.json()
        except json.JSONDecodeError as e:
            raise NetworkError(f"Failed to parse JSON response: {e}")

        # Extract apps from response
        if "response" not in data or "apps" not in data["response"]:
            raise SteamAPIError("Unexpected API response format")

        apps = data["response"]["apps"]
        all_apps.extend(apps)

        print(f"Page {page_count}: Fetched {len(apps)} apps (Total: {len(all_apps)})")

        # Check if there are more results
        have_more = data["response"].get("have_more_results", False)
        if not have_more:
            break

        # Update last_appid for next request
        last_appid = data["response"].get("last_appid")
        if last_appid is None:
            break

    print(f"✓ Completed! Total apps fetched: {len(all_apps)}")
    return all_apps


def fetch_apps_sample(
    count: int = 100,
    api_key: Optional[str] = None,
    timeout: int = 30
) -> List[Dict[str, Any]]:
    """
    Fetch a random sample of Steam apps.

    This function fetches ALL apps using fetch_all_apps() and then returns
    a random sample of them. This ensures better coverage than fetching
    just the first N apps.

    Args:
        count: Number of apps to fetch (default: 100)
        api_key: Steam Web API key (if None, reads from STEAM_API_KEY env var)
        timeout: Request timeout in seconds (default: 30)

    Returns:
        List of dictionaries containing app information

    Raises:
        APIKeyError: If API key is not provided and not in environment
        NetworkError: If API request fails
        ValueError: If count is invalid
    """
    # Validate parameters
    if count <= 0:
        raise ValueError(f"count must be positive, got {count}")

    print(f"Fetching all apps to select a random sample of {count}...")

    # Fetch all apps first
    # We don't verify API key here as fetch_all_apps will do it
    all_apps = fetch_all_apps(
        api_key=api_key,
        max_results=50000,  # Use max batch size for efficiency
        timeout=timeout
    )

    if not all_apps:
        print("Warning: No apps found.")
        return []

    # Sample from the list
    if count >= len(all_apps):
        print(f"Requested count {count} >= total apps {len(all_apps)}. Returning all apps.")
        return all_apps

    sampled_apps = random.sample(all_apps, count)
    print(f"✓ Selected {len(sampled_apps)} random apps from {len(all_apps)} total apps")

    return sampled_apps
