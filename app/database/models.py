import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import Column, String, DateTime, Text, Boolean, ForeignKey, Float, UniqueConstraint, Index, JSON
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class Story(Base):
    """
    Represents one underlying news event or topic.
    Multiple ContentItems from different sources may belong to the same Story.
    """
    __tablename__ = "stories"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    title = Column(String, nullable=False)
    first_seen_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    last_updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    story_content = relationship("StoryContent", back_populates="story", cascade="all, delete-orphan")


class StoryContent(Base):
    """
    Association table linking one Story to many ContentItems.
    One ContentItem may belong to at most one Story (unique constraint on content_item_id).
    """
    __tablename__ = "story_content"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    story_id = Column(String, ForeignKey("stories.id"), nullable=False, index=True)
    content_item_id = Column(String, ForeignKey("content_items.id"), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    story = relationship("Story", back_populates="story_content")
    content_item = relationship("ContentItem", back_populates="story_content")

    __table_args__ = (
        UniqueConstraint("content_item_id", name="uq_story_content_item"),
    )



class Source(Base):
    __tablename__ = "sources"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, nullable=False)
    source_type = Column(String, nullable=False) # e.g. youtube, rss, web
    base_url = Column(String, nullable=True)
    reliability_score = Column(Float, default=1.0)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    content_items = relationship("ContentItem", back_populates="source")


class ContentItem(Base):
    __tablename__ = "content_items"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    source_id = Column(String, ForeignKey("sources.id"), nullable=False)
    external_id = Column(String, nullable=False, unique=True, index=True)
    content_type = Column(String, nullable=False)
    title = Column(String, nullable=False)
    url = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    author = Column(String, nullable=True)
    raw_content = Column(Text, nullable=True)
    transcript = Column(Text, nullable=True)
    published_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    source = relationship("Source", back_populates="content_items")
    digests = relationship("Digest", back_populates="content_item")
    story_content = relationship("StoryContent", back_populates="content_item", uselist=False)
    enrichment = relationship(
        "ContentEnrichment", back_populates="content_item", uselist=False,
        cascade="all, delete-orphan",
    )


class ContentEnrichment(Base):
    __tablename__ = "content_enrichments"
    __table_args__ = (Index("ix_content_enrichments_category", "category"),)

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    content_item_id = Column(
        String, ForeignKey("content_items.id"), nullable=False, unique=True, index=True
    )
    category = Column(String, nullable=False)
    topics = Column(JSON, nullable=False, default=list)
    entities = Column(JSON, nullable=False, default=list)
    importance = Column(Float, nullable=False)
    novelty = Column(Float, nullable=False)
    technical_depth = Column(Float, nullable=False)
    impact = Column(Float, nullable=False)
    source_quality = Column(Float, nullable=False)
    model_name = Column(String, nullable=False)
    prompt_version = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    content_item = relationship("ContentItem", back_populates="enrichment")


class YouTubeVideo(Base):
    __tablename__ = "youtube_videos"
    
    video_id = Column(String, primary_key=True)
    title = Column(String, nullable=False)
    url = Column(String, nullable=False)
    channel_id = Column(String, nullable=False)
    published_at = Column(DateTime, nullable=False)
    description = Column(Text)
    transcript = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class OpenAIArticle(Base):
    __tablename__ = "openai_articles"
    
    guid = Column(String, primary_key=True)
    title = Column(String, nullable=False)
    url = Column(String, nullable=False)
    description = Column(Text)
    published_at = Column(DateTime, nullable=False)
    category = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class AnthropicArticle(Base):
    __tablename__ = "anthropic_articles"
    
    guid = Column(String, primary_key=True)
    title = Column(String, nullable=False)
    url = Column(String, nullable=False)
    description = Column(Text)
    published_at = Column(DateTime, nullable=False)
    category = Column(String, nullable=True)
    markdown = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class Digest(Base):
    __tablename__ = "digests"
    
    id = Column(String, primary_key=True)
    content_item_id = Column(String, ForeignKey("content_items.id"), nullable=True)
    article_type = Column(String, nullable=True)
    article_id = Column(String, nullable=True)
    url = Column(String, nullable=False)
    title = Column(String, nullable=False)
    summary = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    content_item = relationship("ContentItem", back_populates="digests")
