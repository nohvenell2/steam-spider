"""CRUD operations for Steam game data"""

import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List, Tuple

from sqlalchemy.orm import Session

from dbwriter.db.models import BasicInfo, Genre, Tag, Review

logger = logging.getLogger(__name__)


def insert_game_data(session: Session, game_info: Dict[str, Any]) -> BasicInfo:
    """
    Insert or update complete game data.

    This function takes game data and inserts it into the database.
    If the game already exists, it updates the data.

    Args:
        session: SQLAlchemy database session
        game_info: Dictionary containing game data

    Returns:
        BasicInfo ORM object

    Expected game_info structure:
        {
            "game_id": int,
            "url": str,
            "title": str,
            "description": str,
            "header_image": str,
            "genres": list,          # ["Action", "RPG", ...]
            "developer": str,
            "publisher": str,
            "release_date": datetime or None,  # IMPORTANT: datetime object, not string
            "release_date_original": str or None,  # Original date string from Steam
            "tags": list,            # ["Singleplayer", "Atmospheric", ...]
            "reviews": {
                "total_review_count": int,
                "all_reviews": str,
                "total_review_positive_percent": int,
                "recent_review_count": int,
                "recent_reviews": str,
                "recent_review_positive_percent": int
            }
        }
    """
    game_id = game_info.get("game_id")

    # Check if game exists
    game = session.query(BasicInfo).filter_by(game_id=game_id).first()

    if game:
        # Update existing game
        game.url = game_info.get("url")
        game.title = game_info.get("title")
        game.description = game_info.get("description")
        game.header_image = game_info.get("header_image")
        game.developer = game_info.get("developer")
        game.publisher = game_info.get("publisher")
        game.release_date = game_info.get("release_date")  # datetime object
        game.release_date_original = game_info.get("release_date_original")  # original string
        game.updated_at = datetime.now(timezone.utc)  # type: ignore  # Explicitly update timestamp

        # Delete existing genres and tags
        session.query(Genre).filter_by(game_id=game_id).delete()
        session.query(Tag).filter_by(game_id=game_id).delete()
    else:
        # Create new game
        game = BasicInfo(
            game_id=game_id,
            url=game_info.get("url"),
            title=game_info.get("title"),
            description=game_info.get("description"),
            header_image=game_info.get("header_image"),
            developer=game_info.get("developer"),
            publisher=game_info.get("publisher"),
            release_date=game_info.get("release_date"),  # datetime object
            release_date_original=game_info.get("release_date_original"),  # original string
        )
        session.add(game)

    # Insert genres
    for genre_name in game_info.get("genres", []):
        if genre_name:
            genre = Genre(game_id=game_id, genre_name=genre_name)
            session.add(genre)

    # Insert tags
    for tag_name in game_info.get("tags", []):
        if tag_name:
            tag = Tag(game_id=game_id, tag_name=tag_name)
            session.add(tag)

    # Insert or update reviews
    reviews_data = game_info.get("reviews", {})
    review = session.query(Review).filter_by(game_id=game_id).first()

    if review:
        # Update existing review
        review.total_review_count = reviews_data.get("total_review_count")
        review.all_reviews = reviews_data.get("all_reviews")
        review.total_review_positive_percent = reviews_data.get("total_review_positive_percent")
        review.recent_review_count = reviews_data.get("recent_review_count")
        review.recent_reviews = reviews_data.get("recent_reviews")
        review.recent_review_positive_percent = reviews_data.get("recent_review_positive_percent")
        review.updated_at = datetime.now(timezone.utc)  # type: ignore  # Explicitly update timestamp
    else:
        # Create new review
        review = Review(
            game_id=game_id,
            total_review_count=reviews_data.get("total_review_count"),
            all_reviews=reviews_data.get("all_reviews"),
            total_review_positive_percent=reviews_data.get("total_review_positive_percent"),
            recent_review_count=reviews_data.get("recent_review_count"),
            recent_reviews=reviews_data.get("recent_reviews"),
            recent_review_positive_percent=reviews_data.get("recent_review_positive_percent"),
        )
        session.add(review)

    session.flush()
    return game


def bulk_insert_games(session: Session, games_data: List[Dict[str, Any]]) -> Tuple[int, List[Dict[str, Any]]]:
    """
    Bulk insert multiple games using savepoints for individual error handling.

    Each game is processed within a savepoint (nested transaction).
    If one game fails, only that game is rolled back - other games are still inserted.

    Args:
        session: SQLAlchemy database session
        games_data: List of game info dictionaries

    Returns:
        Number of games successfully inserted

    Example:
        >>> games = [game_info1, game_info2, game_info3]
        >>> with get_session_context() as session:
        ...     count = bulk_insert_games(session, games)
        ...     print(f"Inserted {count} games")
    """
    success_count = 0
    failed_savings = []

    for game_info in games_data:
        game_id = game_info.get("game_id", "unknown")

        # Create savepoint for this game
        savepoint = session.begin_nested()

        try:
            insert_game_data(session, game_info)
            session.flush()  # Force DB validation before committing savepoint
            savepoint.commit()  # Confirm this game's changes to main transaction
            success_count += 1

        except Exception as e:
            # Rollback only this game's changes
            savepoint.rollback()

            # Log detailed error information
            error_type = type(e).__name__
            logger.error(
                f"Failed to insert game | game_id={game_id} | "
                f"error_type={error_type} | error={str(e)}"
            )
            
            # Collect failed saving games
            failed_savings.append({
                "game_id": game_id,
                "error": str(e),
                "data": game_info
            })

            # Continue processing remaining games

    return success_count, failed_savings




def game_exists(session: Session, game_id: int) -> bool:
    """
    Check if a game exists in the database.

    Args:
        session: SQLAlchemy database session
        game_id: Steam application ID

    Returns:
        True if game exists, False otherwise
    """
    return session.query(BasicInfo).filter_by(game_id=game_id).first() is not None


def get_games_count(session: Session) -> int:
    """
    Get total number of games in the database.

    Args:
        session: SQLAlchemy database session

    Returns:
        Number of games
    """
    return session.query(BasicInfo).count()
