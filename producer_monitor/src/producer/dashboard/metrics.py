"""Progress and metrics calculation."""

from typing import Dict, Any
from .monitor import QueueSnapshot


def calculate_progress(data: QueueSnapshot) -> Dict[str, Any]:
    """
    Calculate progress metrics.

    Args:
        total_games: Total number of games to process
        work_remaining: Number of jobs still in work queue

    Returns:
        Dictionary with progress metrics:
            - total: Total games
            - completed: Games completed (updated_games + crawling_failed + saving_failed)
            - remaining: Games remaining (total_games - completed)
            - percent: Progress percentage (0-100)
    """
    total_games = data.total_games
    
    if total_games == 0:
        return {
            "total": 0,
            "completed": 0,
            "remaining": 0,
            "percent": 0.0
        }
    
    completed = data.updated_games + data.crawling_failed + data.saving_failed
    work_remaining = total_games - completed
    percent = (completed / total_games) * 100.0

    return {
        "total": total_games,
        "completed": completed,
        "remaining": work_remaining,
        "percent": round(percent, 2)
    }


def format_number(num: int) -> str:
    """
    Format number with thousands separator.

    Args:
        num: Number to format

    Returns:
        Formatted string (e.g., "140,000")
    """
    return f"{num:,}"
