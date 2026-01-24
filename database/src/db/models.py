"""SQLAlchemy ORM models for Steam game data"""

from datetime import datetime
from typing import List
from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    ForeignKey,
    DateTime,
    Index,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class BasicInfo(Base):
    """Basic game information table"""

    __tablename__ = "basic_info"

    game_id = Column(Integer, primary_key=True, index=True)
    url = Column(String(500), nullable=False)
    title = Column(String(500))
    description = Column(Text)
    header_image = Column(String(500))
    developer = Column(String(200))
    publisher = Column(String(200))
    release_date = Column(DateTime, nullable=True)
    release_date_original = Column(String(200), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    genres = relationship("Genre", back_populates="game", cascade="all, delete-orphan")
    tags = relationship("Tag", back_populates="game", cascade="all, delete-orphan")
    reviews = relationship("Review", back_populates="game", uselist=False, cascade="all, delete-orphan")

    def __repr__(self):
        return f"<BasicInfo(game_id={self.game_id}, title='{self.title}')>"


class Genre(Base):
    """Game genres table (Many-to-Many)"""

    __tablename__ = "genres"

    id = Column(Integer, primary_key=True, autoincrement=True)
    game_id = Column(Integer, ForeignKey("basic_info.game_id", ondelete="CASCADE"), nullable=False)
    genre_name = Column(String(100), nullable=False)

    # Relationship
    game = relationship("BasicInfo", back_populates="genres")

    # Indexes
    __table_args__ = (
        Index("idx_genres_game_id", "game_id"),
        Index("idx_genres_unique", "game_id", "genre_name", unique=True),
    )

    def __repr__(self):
        return f"<Genre(game_id={self.game_id}, genre='{self.genre_name}')>"


class Tag(Base):
    """Game tags table (Many-to-Many)"""

    __tablename__ = "tags"

    id = Column(Integer, primary_key=True, autoincrement=True)
    game_id = Column(Integer, ForeignKey("basic_info.game_id", ondelete="CASCADE"), nullable=False)
    tag_name = Column(String(100), nullable=False)

    # Relationship
    game = relationship("BasicInfo", back_populates="tags")

    # Indexes
    __table_args__ = (
        Index("idx_tags_game_id", "game_id"),
        Index("idx_tags_unique", "game_id", "tag_name", unique=True),
    )

    def __repr__(self):
        return f"<Tag(game_id={self.game_id}, tag='{self.tag_name}')>"


class Review(Base):
    """Game reviews table (1:1 with BasicInfo)"""

    __tablename__ = "reviews"

    game_id = Column(Integer, ForeignKey("basic_info.game_id", ondelete="CASCADE"), primary_key=True)
    total_review_count = Column(Integer)
    all_reviews = Column(String(100))
    total_review_positive_percent = Column(Integer)
    recent_review_count = Column(Integer)
    recent_reviews = Column(String(100))
    recent_review_positive_percent = Column(Integer)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationship
    game = relationship("BasicInfo", back_populates="reviews")

    def __repr__(self):
        return f"<Review(game_id={self.game_id}, all_reviews='{self.all_reviews}')>"