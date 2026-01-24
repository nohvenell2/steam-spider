"""Data validation and sanitization for game data"""

import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class DataValidator:
    """
    Validates and sanitizes game data before database insertion.

    Automatically truncates fields that exceed database column limits.
    """

    # Field length limits (matching database schema)
    FIELD_LIMITS = {
        "url": 500,
        "title": 500,
        "header_image": 500,
        "developer": 200,
        "publisher": 200,
        "release_date_original": 200,
        "all_reviews": 100,
        "recent_reviews": 100,
        "genre_name": 100,
        "tag_name": 100,
    }

    @staticmethod
    def validate_and_sanitize(game_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate and sanitize game data.

        Truncates string fields that exceed database limits.
        Logs warnings when truncation occurs.

        Args:
            game_data: Raw game data dictionary

        Returns:
            Sanitized game data dictionary
        """
        sanitized = game_data.copy()
        game_id = sanitized.get("game_id", "unknown")

        # Validate and truncate top-level fields
        for field, max_length in DataValidator.FIELD_LIMITS.items():
            if field in sanitized and isinstance(sanitized[field], str):
                original_value = sanitized[field]
                if len(original_value) > max_length:
                    sanitized[field] = original_value[:max_length]
                    logger.warning(
                        f"Field truncated | game_id={game_id} | field={field} | "
                        f"original_length={len(original_value)} | truncated_to={max_length}"
                    )

        # Validate and truncate genres
        if "genres" in sanitized and isinstance(sanitized["genres"], list):
            sanitized["genres"] = [
                DataValidator._truncate_string(genre, "genre_name", game_id)
                for genre in sanitized["genres"]
            ]

        # Validate and truncate tags
        if "tags" in sanitized and isinstance(sanitized["tags"], list):
            sanitized["tags"] = [
                DataValidator._truncate_string(tag, "tag_name", game_id)
                for tag in sanitized["tags"]
            ]

        # Validate and truncate review fields
        if "reviews" in sanitized and isinstance(sanitized["reviews"], dict):
            reviews = sanitized["reviews"]
            for field in ["all_reviews", "recent_reviews"]:
                if field in reviews and isinstance(reviews[field], str):
                    max_length = DataValidator.FIELD_LIMITS[field]
                    original_value = reviews[field]
                    if len(original_value) > max_length:
                        reviews[field] = original_value[:max_length]
                        logger.warning(
                            f"Review field truncated | game_id={game_id} | field={field} | "
                            f"original_length={len(original_value)} | truncated_to={max_length}"
                        )

        return sanitized

    @staticmethod
    def _truncate_string(value: str, field_type: str, game_id: Any) -> str:
        """
        Truncate a string to the maximum length for its field type.

        Args:
            value: String value to truncate
            field_type: Type of field (genre_name, tag_name, etc.)
            game_id: Game ID for logging

        Returns:
            Truncated string
        """
        if not isinstance(value, str):
            return value

        max_length = DataValidator.FIELD_LIMITS.get(field_type, 100)
        if len(value) > max_length:
            truncated = value[:max_length]
            logger.warning(
                f"Item truncated | game_id={game_id} | type={field_type} | "
                f"original_length={len(value)} | truncated_to={max_length} | "
                f"original='{value[:50]}...'"
            )
            return truncated

        return value

    @staticmethod
    def validate_game_id(game_data: Dict[str, Any]) -> Optional[int]:
        """
        Validate and extract game_id from game data.

        Args:
            game_data: Game data dictionary

        Returns:
            Valid game_id or None if invalid
        """
        game_id = game_data.get("game_id")

        if game_id is None:
            logger.error("Missing game_id in game data")
            return None

        if not isinstance(game_id, int):
            try:
                game_id = int(game_id)
            except (ValueError, TypeError):
                logger.error(f"Invalid game_id type | game_id={game_id} | type={type(game_id)}")
                return None

        return game_id
