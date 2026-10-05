from datetime import datetime, timedelta, timezone
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from .models import (
    Source,
    ContentItem,
    Digest,
    ContentEnrichment,
    ContentEmbedding,
    StoryContent,
    Story,
)
from .connection import get_session


class Repository:
    def __init__(self, session: Optional[Session] = None):
        self.session = session or get_session()
        
    def _get_or_create_source(self, name: str, source_type: str) -> Source:
        source = self.session.query(Source).filter_by(name=name, source_type=source_type).first()
        if not source:
            source = Source(name=name, source_type=source_type)
            self.session.add(source)
            self.session.flush()
        return source

    def create_content_item(self, source_name: str, source_type: str, external_id: str, 
                            content_type: str, title: str, url: str, published_at: datetime, 
                            description: str = "", raw_content: Optional[str] = None, 
                            transcript: Optional[str] = None) -> Optional[ContentItem]:
        existing = self.session.query(ContentItem).filter_by(external_id=external_id).first()
        if existing:
            return None
            
        source = self._get_or_create_source(source_name, source_type)
        
        item = ContentItem(
            source_id=source.id,
            external_id=external_id,
            content_type=content_type,
            title=title,
            url=url,
            published_at=published_at,
            description=description,
            raw_content=raw_content,
            transcript=transcript
        )
        self.session.add(item)
        self.session.commit()
        return item
        
    def bulk_create_content_items(self, source_name: str, source_type: str, items: List[dict]) -> int:
        source = self._get_or_create_source(source_name, source_type)
        
        new_items = []
        for i in items:
            existing = self.session.query(ContentItem).filter_by(external_id=i["external_id"]).first()
            if not existing:
                new_items.append(ContentItem(
                    source_id=source.id,
                    external_id=i["external_id"],
                    content_type=i.get("content_type", "article"),
                    title=i["title"],
                    url=i["url"],
                    published_at=i["published_at"],
                    description=i.get("description", ""),
                    raw_content=i.get("raw_content"),
                    transcript=i.get("transcript")
                ))
                
        if new_items:
            self.session.add_all(new_items)
            self.session.commit()
        return len(new_items)

    def get_content_item_by_external_id(self, external_id: str) -> Optional[ContentItem]:
        return self.session.query(ContentItem).filter_by(external_id=external_id).first()

    def list_content_items(
        self, page: int = 1, page_size: int = 20,
        source_name: Optional[str] = None, content_type: Optional[str] = None,
    ):
        query = self.session.query(ContentItem).join(Source)
        if source_name:
            query = query.filter(Source.name == source_name)
        if content_type:
            query = query.filter(ContentItem.content_type == content_type)
        total = query.count()
        items = (
            query.order_by(ContentItem.published_at.desc())
            .offset((page - 1) * page_size).limit(page_size).all()
        )
        return items, total

    def list_stories(self, page: int = 1, page_size: int = 20):
        query = self.session.query(Story)
        total = query.count()
        stories = (
            query.order_by(Story.last_updated_at.desc())
            .offset((page - 1) * page_size).limit(page_size).all()
        )
        return stories, total

    def create_content_enrichment(
        self, content_item_id: str, result: Any, model_name: str, prompt_version: str
    ) -> Optional[ContentEnrichment]:
        if self.get_content_enrichment(content_item_id) is not None:
            return None
        if self.session.query(ContentItem).filter_by(id=content_item_id).first() is None:
            return None
        enrichment = ContentEnrichment(
            content_item_id=content_item_id,
            category=result.category.value if hasattr(result.category, "value") else result.category,
            topics=list(result.topics),
            entities=list(result.entities),
            importance=result.importance,
            novelty=result.novelty,
            technical_depth=result.technical_depth,
            impact=result.impact,
            source_quality=result.source_quality,
            model_name=model_name,
            prompt_version=prompt_version,
        )
        self.session.add(enrichment)
        self.session.commit()
        return enrichment

    def get_content_enrichment(self, content_item_id: str) -> Optional[ContentEnrichment]:
        return self.session.query(ContentEnrichment).filter_by(
            content_item_id=content_item_id
        ).first()

    def upsert_content_enrichment(
        self, content_item_id: str, result: Any, model_name: str, prompt_version: str
    ) -> Optional[ContentEnrichment]:
        enrichment = self.get_content_enrichment(content_item_id)
        if enrichment is None:
            return self.create_content_enrichment(
                content_item_id, result, model_name, prompt_version
            )
        enrichment.category = (
            result.category.value if hasattr(result.category, "value") else result.category
        )
        enrichment.topics = list(result.topics)
        enrichment.entities = list(result.entities)
        enrichment.importance = result.importance
        enrichment.novelty = result.novelty
        enrichment.technical_depth = result.technical_depth
        enrichment.impact = result.impact
        enrichment.source_quality = result.source_quality
        enrichment.model_name = model_name
        enrichment.prompt_version = prompt_version
        self.session.commit()
        return enrichment

    def delete_content_enrichment(self, content_item_id: str) -> bool:
        enrichment = self.get_content_enrichment(content_item_id)
        if enrichment is None:
            return False
        self.session.delete(enrichment)
        self.session.commit()
        return True

    def get_content_embedding(self, content_item_id: str) -> Optional[ContentEmbedding]:
        return self.session.query(ContentEmbedding).filter_by(
            content_item_id=content_item_id
        ).first()

    def get_embedding_by_content_item(
        self, content_item_id: str
    ) -> Optional[ContentEmbedding]:
        return self.get_content_embedding(content_item_id)

    def create_content_embedding(
        self,
        content_item_id: str,
        embedding: List[float],
        embedding_model: str,
        dimensions: int,
        text_hash: str,
    ) -> Optional[ContentEmbedding]:
        if self.get_content_embedding(content_item_id) is not None:
            return None
        if self.session.query(ContentItem).filter_by(id=content_item_id).first() is None:
            return None
        record = ContentEmbedding(
            content_item_id=content_item_id,
            embedding=embedding,
            embedding_model=embedding_model,
            dimensions=dimensions,
            text_hash=text_hash,
        )
        self.session.add(record)
        self.session.commit()
        return record

    def upsert_content_embedding(
        self,
        content_item_id: str,
        embedding: List[float],
        embedding_model: str,
        dimensions: int,
        text_hash: str,
    ) -> ContentEmbedding:
        record = self.get_content_embedding(content_item_id)
        if record is None:
            record = self.create_content_embedding(
                content_item_id, embedding, embedding_model, dimensions, text_hash
            )
            if record is None:
                raise RuntimeError("Could not create ContentEmbedding")
            return record
        record.embedding = embedding
        record.embedding_model = embedding_model
        record.dimensions = dimensions
        record.text_hash = text_hash
        self.session.commit()
        return record

    def find_similar_content(
        self,
        embedding: List[float],
        limit: int = 10,
        exclude_content_item_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        distance = ContentEmbedding.embedding.cosine_distance(embedding)
        query = self.session.query(
            ContentItem, StoryContent.story_id, distance.label("distance")
        ).join(
            ContentEmbedding, ContentEmbedding.content_item_id == ContentItem.id
        ).outerjoin(StoryContent, StoryContent.content_item_id == ContentItem.id)
        if exclude_content_item_id:
            query = query.filter(ContentItem.id != exclude_content_item_id)
        return [
            {
                "content_item": item,
                "story_id": story_id,
                "distance": score,
                "similarity": 1.0 - float(score),
            }
            for item, story_id, score in query.order_by(distance).limit(limit).all()
        ]

    def get_trend_records(self, start_time: datetime, end_time: datetime) -> List[Dict[str, Any]]:
        """Return only fields needed by deterministic trend analysis."""
        rows = (
            self.session.query(
                ContentItem.id,
                ContentItem.published_at,
                ContentEnrichment.topics,
                ContentItem.source_id,
                Source.name,
                StoryContent.story_id,
            )
            .join(ContentEnrichment, ContentEnrichment.content_item_id == ContentItem.id)
            .join(Source, Source.id == ContentItem.source_id)
            .outerjoin(StoryContent, StoryContent.content_item_id == ContentItem.id)
            .filter(
                ContentItem.published_at >= start_time,
                ContentItem.published_at < end_time,
            )
            .all()
        )
        return [
            {
                "content_item_id": item_id,
                "published_at": published_at,
                "topics": topics or [],
                "source_id": source_id,
                "source_name": source_name,
                "story_id": story_id,
            }
            for item_id, published_at, topics, source_id, source_name, story_id in rows
        ]
        
    # Legacy wrapper methods for backwards compatibility
    def bulk_create_youtube_videos(self, videos: List[dict]) -> int:
        items = []
        for v in videos:
            items.append({
                "external_id": v["video_id"],
                "content_type": "video",
                "title": v["title"],
                "url": v["url"],
                "published_at": v["published_at"],
                "description": v.get("description", ""),
                "transcript": v.get("transcript")
            })
        return self.bulk_create_content_items("YouTube", "youtube", items)
    
    def bulk_create_openai_articles(self, articles: List[dict]) -> int:
        items = []
        for a in articles:
            items.append({
                "external_id": a["guid"],
                "content_type": "article",
                "title": a["title"],
                "url": a["url"],
                "published_at": a["published_at"],
                "description": a.get("description", "")
            })
        return self.bulk_create_content_items("OpenAI RSS", "rss", items)
    
    def bulk_create_anthropic_articles(self, articles: List[dict]) -> int:
        items = []
        for a in articles:
            items.append({
                "external_id": a["guid"],
                "content_type": "article",
                "title": a["title"],
                "url": a["url"],
                "published_at": a["published_at"],
                "description": a.get("description", "")
            })
        return self.bulk_create_content_items("Anthropic RSS", "rss", items)
    
    def get_anthropic_articles_without_markdown(self, limit: Optional[int] = None) -> List[ContentItem]:
        query = self.session.query(ContentItem).join(Source).filter(
            Source.name == "Anthropic RSS",
            ContentItem.raw_content.is_(None)
        )
        if limit:
            query = query.limit(limit)
        return query.all()
    
    def update_anthropic_article_markdown(self, guid: str, markdown: str) -> bool:
        article = self.session.query(ContentItem).filter_by(external_id=guid).first()
        if article:
            article.raw_content = markdown
            self.session.commit()
            return True
        return False
    
    def get_youtube_videos_without_transcript(self, limit: Optional[int] = None) -> List[ContentItem]:
        query = self.session.query(ContentItem).join(Source).filter(
            Source.name == "YouTube",
            ContentItem.transcript.is_(None)
        )
        if limit:
            query = query.limit(limit)
        return query.all()
    
    def update_youtube_video_transcript(self, video_id: str, transcript: str) -> bool:
        video = self.session.query(ContentItem).filter_by(external_id=video_id).first()
        if video:
            video.transcript = transcript
            self.session.commit()
            return True
        return False
    
    def get_articles_without_digest(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        articles = []
        seen_ids = set()
        
        digests = self.session.query(Digest).all()
        for d in digests:
            if d.content_item_id:
                seen_ids.add(d.content_item_id)
            elif d.article_id:
                seen_ids.add(d.article_id) # fallback for old unmigrated data
        
        # Get all content items that don't have a digest
        query = self.session.query(ContentItem).filter(
            ContentItem.id.notin_(list(seen_ids)),
            ContentItem.external_id.notin_(list(seen_ids))
        )
        
        # Filter for items that are ready for digest (have transcript or markdown, or don't need it)
        all_items = query.all()
        
        for item in all_items:
            # Skip youtube videos without transcripts
            if item.source.name == "YouTube" and (not item.transcript or item.transcript == "__UNAVAILABLE__"):
                continue
            # Skip anthropic articles without markdown
            if item.source.name == "Anthropic RSS" and not item.raw_content:
                continue
                
            content = item.transcript or item.raw_content or item.description or ""
            
            articles.append({
                "type": item.source.name.lower().split(" ")[0], # e.g. 'youtube', 'openai', 'anthropic'
                "id": item.external_id,
                "content_item_id": item.id,
                "title": item.title,
                "url": item.url,
                "content": content,
                "published_at": item.published_at
            })
            
        if limit:
            articles = articles[:limit]
            
        return articles
    
    def create_digest(self, article_type: str, article_id: str, url: str, title: str, summary: str, published_at: Optional[datetime] = None, content_item_id: Optional[str] = None) -> Optional[Digest]:
        digest_id = f"{article_type}:{article_id}"
        existing = self.session.query(Digest).filter_by(id=digest_id).first()
        if existing:
            return None
            
        if not content_item_id:
            # Try to lookup content item
            item = self.session.query(ContentItem).filter_by(external_id=article_id).first()
            if item:
                content_item_id = item.id
        
        if published_at:
            if published_at.tzinfo is None:
                published_at = published_at.replace(tzinfo=timezone.utc)
            created_at = published_at
        else:
            created_at = datetime.now(timezone.utc)
        
        digest = Digest(
            id=digest_id,
            content_item_id=content_item_id,
            article_type=article_type,
            article_id=article_id,
            url=url,
            title=title,
            summary=summary,
            created_at=created_at
        )
        self.session.add(digest)
        self.session.commit()
        return digest
    
    def get_recent_digests(self, hours: int = 24) -> List[Dict[str, Any]]:
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours)
        digests = self.session.query(Digest).filter(
            Digest.created_at >= cutoff_time
        ).order_by(Digest.created_at.desc()).all()
        
        return [
            {
                "id": d.id,
                "article_type": d.article_type,
                "article_id": d.article_id,
                "content_item_id": d.content_item_id,
                "url": d.url,
                "title": d.title,
                "summary": d.summary,
                "created_at": d.created_at
            }
            for d in digests
        ]
