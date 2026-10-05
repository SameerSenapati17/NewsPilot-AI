import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import Column, String, DateTime, Text, Boolean, ForeignKey, Float
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


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

