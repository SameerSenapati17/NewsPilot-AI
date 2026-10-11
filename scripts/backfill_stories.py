import logging

from app.database.models import ContentItem, Story
from app.database.repository import Repository
from app.story_clustering import cluster_content_item


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    repo = Repository()
    created_stories = 0
    associations = 0
    items = repo.session.query(ContentItem).order_by(ContentItem.published_at.asc()).all()
    for item in items:
        if item.story_content is not None:
            continue
        try:
            before = repo.session.query(Story).count()
            story = cluster_content_item(repo, item)
            associations += 1
            if repo.session.query(Story).count() > before:
                created_stories += 1
            logging.info("Associated %s with Story %s", item.external_id, story.id)
        except Exception as exc:
            logging.error("Could not associate %s: %s", item.external_id, exc)
    logging.info(
        "Backfill complete: %s Stories created; %s ContentItems associated; story count is %s",
        created_stories,
        associations,
        repo.session.query(Story).count(),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
