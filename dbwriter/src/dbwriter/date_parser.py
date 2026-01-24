"""Date parsing module for multilingual release dates"""

import logging
import re
from datetime import datetime
from typing import Optional
from dateutil import parser as dateutil_parser
from dateutil.parser import ParserError

logger = logging.getLogger(__name__)


class DateParser:
    """
    Parse multilingual release date strings from Steam.

    Supported formats:
    - English: "25 Feb, 2022", "Dec 9, 2020", "February 25, 2022"
    - Korean: "2020년 12월 10일"
    - Japanese: "2020年12月10日"
    - Chinese: "2020年12月10日"
    - Special cases: "Coming Soon", "TBA", "To be announced" → None
    """

    def __init__(self):
        # Special cases that should return None
        self.special_cases = [
            "coming soon",
            "tba",
            "to be announced",
            "출시 예정",  # Korean: Coming Soon
            "미정",      # Korean: TBA
            "未定",      # Japanese/Chinese: TBA
            "近日公開",  # Japanese/Chinese: Coming Soon
        ]

    def parse(self, date_string: str, game_id: int = None) -> Optional[datetime]:
        """
        Parse date string to datetime object.

        Args:
            date_string: Raw date string from Steam
            game_id: Optional game ID for logging purposes

        Returns:
            - Parsed datetime object if successful
            - None if parsing fails or date is incomplete

        Examples:
            >>> parser = DateParser()
            >>> parser.parse("25 Feb, 2022")
            datetime.datetime(2022, 2, 25, 0, 0)
            >>> parser.parse("2020년 12월 10일")
            datetime.datetime(2020, 12, 10, 0, 0)
            >>> parser.parse("Coming Soon")
            None
        """
        # Step 1: Validate input
        if not date_string or not isinstance(date_string, str):
            return None

        date_string = date_string.strip()

        if not date_string:
            return None

        # Step 2: Check special cases
        if self._is_special_case(date_string):
            if game_id:
                logger.debug(f"Special case detected | game_id={game_id} | original='{date_string}'")
            return None

        # Step 3: Try parsing with regex patterns for Asian languages
        asian_date = self._parse_asian_date(date_string)
        if asian_date:
            return asian_date

        # Step 4: Try parsing with strict English date patterns
        english_date = self._parse_english_date(date_string)
        if english_date:
            return english_date

        # Step 5: If no pattern matched, log and return None
        if game_id:
            logger.debug(f"Date parse failed | game_id={game_id} | original='{date_string}'")
        else:
            logger.debug(f"Date parse failed | original='{date_string}'")
        return None

    def _is_special_case(self, date_string: str) -> bool:
        """
        Check if the date string is a special case (Coming Soon, TBA, etc.).

        Args:
            date_string: Date string to check

        Returns:
            True if it's a special case, False otherwise
        """
        date_lower = date_string.lower().strip()
        return any(special.lower() in date_lower for special in self.special_cases)

    def _parse_asian_date(self, date_string: str) -> Optional[datetime]:
        """
        Parse Asian date formats (Korean, Japanese, Chinese).

        Patterns:
        - Korean: "2020년 12월 10일"
        - Japanese/Chinese: "2020年12月10日"

        Args:
            date_string: Date string to parse

        Returns:
            Parsed datetime or None
        """
        # Korean pattern: YYYY년 MM월 DD일
        korean_pattern = r'(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일'
        match = re.search(korean_pattern, date_string)
        if match:
            year = int(match.group(1))
            month = int(match.group(2))
            day = int(match.group(3))
            try:
                return datetime(year, month, day)
            except ValueError:
                return None

        # Japanese/Chinese pattern: YYYY年MM月DD日
        cjk_pattern = r'(\d{4})年\s*(\d{1,2})月\s*(\d{1,2})日'
        match = re.search(cjk_pattern, date_string)
        if match:
            year = int(match.group(1))
            month = int(match.group(2))
            day = int(match.group(3))
            try:
                return datetime(year, month, day)
            except ValueError:
                return None

        return None

    def _parse_english_date(self, date_string: str) -> Optional[datetime]:
        """
        Parse English date formats with strict patterns.

        Accepted patterns:
        - "15 Apr, 2026"
        - "Apr 15, 2026"
        - "15 April, 2026"
        - "April 15, 2026"
        - "2026-04-15" (ISO format)

        Args:
            date_string: Date string to parse

        Returns:
            Parsed datetime or None
        """
        # Pattern 1: "15 Apr, 2026" or "15 April, 2026"
        # DD MMM, YYYY or DD MMMM, YYYY
        pattern1 = r'^(\d{1,2})\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|january|february|march|april|may|june|july|august|september|october|november|december),?\s+(\d{4})$'
        match = re.match(pattern1, date_string.strip(), re.IGNORECASE)
        if match:
            try:
                # Use dateutil to parse the matched string
                parsed = dateutil_parser.parse(date_string, fuzzy=False)
                return parsed
            except (ValueError, ParserError):
                return None

        # Pattern 2: "Apr 15, 2026" or "April 15, 2026"
        # MMM DD, YYYY or MMMM DD, YYYY
        pattern2 = r'^(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|january|february|march|april|may|june|july|august|september|october|november|december)\s+(\d{1,2}),?\s+(\d{4})$'
        match = re.match(pattern2, date_string.strip(), re.IGNORECASE)
        if match:
            try:
                parsed = dateutil_parser.parse(date_string, fuzzy=False)
                return parsed
            except (ValueError, ParserError):
                return None

        # Pattern 3: ISO format "2026-04-15" or "2026/04/15"
        pattern3 = r'^(\d{4})[-/](\d{1,2})[-/](\d{1,2})$'
        match = re.match(pattern3, date_string.strip())
        if match:
            year = int(match.group(1))
            month = int(match.group(2))
            day = int(match.group(3))
            try:
                return datetime(year, month, day)
            except ValueError:
                return None

        return None

    def _is_complete_date(self, dt: datetime) -> bool:
        """
        Check if the datetime object has complete year, month, and day information.

        Args:
            dt: Datetime object to check

        Returns:
            True if year, month, and day are all valid, False otherwise
        """
        # Check that year is reasonable (not default 1900 from parser)
        # and that month and day are present
        return (
            dt.year is not None
            and dt.year > 1900  # Reasonable year check
            and dt.month is not None
            and dt.month >= 1
            and dt.month <= 12
            and dt.day is not None
            and dt.day >= 1
            and dt.day <= 31
        )
