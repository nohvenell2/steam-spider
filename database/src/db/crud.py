"""CRUD operations for Steam game data"""

from typing import Dict, Any, Optional, List
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from src.db.models import BasicInfo, Genre, Tag, Review


def insert_game_data(session: Session, game_info: Dict[str, Any]) -> BasicInfo:
    """
    Insert or update complete game data.

    This function takes the output from crawler.get_all_info() and inserts
    it into the database. If the game already exists, it updates the data.

    Args:
        session: SQLAlchemy database session
        game_info: Dictionary containing game data from crawler

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
            "release_date": str,
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

    Example:
        >>> from src.db.connection import get_session_context
        >>> from src.db.crud import insert_game_data
        >>>
        >>> game_info = {...}  # From crawler
        >>> with get_session_context() as session:
        ...     game = insert_game_data(session, game_info)
        ...     print(f"Inserted game: {game.title}")
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
        game.release_date = game_info.get("release_date")

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
            release_date=game_info.get("release_date"),
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


def get_game_by_id(session: Session, game_id: int) -> Optional[Dict[str, Any]]:
    """
    Retrieve complete game information by game_id.

    Args:
        session: SQLAlchemy database session
        game_id: Steam application ID

    Returns:
        Dictionary containing complete game data in crawler format, or None if not found

    Example:
        >>> with get_session_context() as session:
        ...     game = get_game_by_id(session, 1091500)
        ...     if game:
        ...         print(game['title'])
        ...         print(game['genres'])
    """
    game = session.query(BasicInfo).filter_by(game_id=game_id).first()

    if not game:
        return None

    # Reconstruct crawler format
    game_data = {
        "game_id": game.game_id,
        "url": game.url,
        "title": game.title,
        "description": game.description,
        "header_image": game.header_image,
        "developer": game.developer,
        "publisher": game.publisher,
        "release_date": game.release_date,
        "genres": [genre.genre_name for genre in game.genres],
        "tags": [tag.tag_name for tag in game.tags],
        "reviews": {},
    }

    # Add reviews if exist
    if game.reviews:
        game_data["reviews"] = {
            "total_review_count": game.reviews.total_review_count,
            "all_reviews": game.reviews.all_reviews,
            "total_review_positive_percent": game.reviews.total_review_positive_percent,
            "recent_review_count": game.reviews.recent_review_count,
            "recent_reviews": game.reviews.recent_reviews,
            "recent_review_positive_percent": game.reviews.recent_review_positive_percent,
        }

    return game_data


def game_exists(session: Session, game_id: int) -> bool:
    """
    Check if a game exists in the database.

    Args:
        session: SQLAlchemy database session
        game_id: Steam application ID

    Returns:
        True if game exists, False otherwise

    Example:
        >>> with get_session_context() as session:
        ...     if game_exists(session, 1091500):
        ...         print("Game exists!")
    """
    return session.query(BasicInfo).filter_by(game_id=game_id).first() is not None


def get_all_game_ids(session: Session) -> List[int]:
    """
    Get list of all game IDs in the database.

    Args:
        session: SQLAlchemy database session

    Returns:
        List of game IDs

    Example:
        >>> with get_session_context() as session:
        ...     game_ids = get_all_game_ids(session)
        ...     print(f"Total games: {len(game_ids)}")
    """
    result = session.query(BasicInfo.game_id).order_by(BasicInfo.game_id).all()
    return [row[0] for row in result]


def get_games_count(session: Session) -> int:
    """
    Get total number of games in the database.

    Args:
        session: SQLAlchemy database session

    Returns:
        Number of games

    Example:
        >>> with get_session_context() as session:
        ...     count = get_games_count(session)
        ...     print(f"Total games: {count}")
    """
    return session.query(BasicInfo).count()


def delete_game(session: Session, game_id: int) -> bool:
    """
    Delete a game and all related data (cascades to genres, tags, reviews).

    Args:
        session: SQLAlchemy database session
        game_id: Steam application ID

    Returns:
        True if game was deleted, False if game didn't exist

    Example:
        >>> with get_session_context() as session:
        ...     if delete_game(session, 1091500):
        ...         print("Game deleted successfully")
    """
    game = session.query(BasicInfo).filter_by(game_id=game_id).first()

    if not game:
        return False

    session.delete(game)
    session.flush()
    return True


def get_games_by_genre(session: Session, genre_name: str, limit: int = 100) -> List[Dict[str, Any]]:
    """
    Get games by genre name.

    Args:
        session: SQLAlchemy database session
        genre_name: Genre to search for
        limit: Maximum number of results (default: 100)

    Returns:
        List of game dictionaries

    Example:
        >>> with get_session_context() as session:
        ...     rpg_games = get_games_by_genre(session, "RPG", limit=10)
        ...     for game in rpg_games:
        ...         print(game['title'])
    """
    games = (
        session.query(BasicInfo)
        .join(Genre)
        .filter(Genre.genre_name == genre_name)
        .limit(limit)
        .all()
    )

    return [
        {
            "game_id": game.game_id,
            "title": game.title,
            "url": game.url,
            "developer": game.developer,
            "release_date": game.release_date,
        }
        for game in games
    ]


def get_games_by_tag(session: Session, tag_name: str, limit: int = 100) -> List[Dict[str, Any]]:
    """
    Get games by tag name.

    Args:
        session: SQLAlchemy database session
        tag_name: Tag to search for
        limit: Maximum number of results (default: 100)

    Returns:
        List of game dictionaries

    Example:
        >>> with get_session_context() as session:
        ...     multiplayer_games = get_games_by_tag(session, "Multiplayer", limit=10)
        ...     for game in multiplayer_games:
        ...         print(game['title'])
    """
    games = (
        session.query(BasicInfo)
        .join(Tag)
        .filter(Tag.tag_name == tag_name)
        .limit(limit)
        .all()
    )

    return [
        {
            "game_id": game.game_id,
            "title": game.title,
            "url": game.url,
            "developer": game.developer,
            "release_date": game.release_date,
        }
        for game in games
    ]


def bulk_insert_games(session: Session, games_data: List[Dict[str, Any]]) -> int:
    """
    Bulk insert multiple games for better performance.

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
    count = 0
    for game_info in games_data:
        try:
            insert_game_data(session, game_info)
            count += 1
        except IntegrityError:
            session.rollback()
            continue

    return count