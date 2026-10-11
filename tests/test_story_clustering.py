import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.story_clustering import cluster_content_item, normalize_title, title_similarity


class TestStoryClustering(unittest.TestCase):
    def item(self, item_id, title, published_at):
        return SimpleNamespace(
            id=item_id,
            title=title,
            published_at=published_at,
            story_content=None,
        )

    def repo(self, candidates=(), items_by_story=None):
        repo = Mock()
        repo.session = Mock()
        repo.find_candidate_stories.return_value = list(candidates)
        repo.get_story_content_items.side_effect = (
            lambda story_id: (items_by_story or {}).get(story_id, [])
        )
        repo.get_story.side_effect = lambda story_id: next(
            (story for story in candidates if story.id == story_id), None
        )
        return repo

    def test_title_normalization(self):
        self.assertEqual(normalize_title("The AI: Model Release!"), {"ai", "model", "release"})

    def test_jaccard_similarity(self):
        self.assertAlmostEqual(
            title_similarity("AI model release", "AI model release update"), 3 / 4
        )

    def test_high_confidence_match_attaches_to_existing_story(self):
        published = datetime(2026, 1, 1)
        story = SimpleNamespace(id="story-1", title="AI model release", last_updated_at=published)
        existing = self.item("old", "AI model release update", published)
        repo = self.repo([story], {"story-1": [existing]})
        result = cluster_content_item(repo, self.item("new", "AI model release", published))
        self.assertIs(result, story)
        repo.create_story.assert_not_called()
        repo.attach_content_item_to_story.assert_called_once_with("story-1", "new")

    def test_low_confidence_creates_new_story(self):
        published = datetime(2026, 1, 1)
        story = SimpleNamespace(id="story-1", title="AI model release", last_updated_at=published)
        repo = self.repo([story], {"story-1": [self.item("old", "AI model release", published)]})
        new_story = SimpleNamespace(id="story-2", last_updated_at=published)
        repo.create_story.return_value = new_story
        result = cluster_content_item(repo, self.item("new", "European football final", published))
        self.assertIs(result, new_story)
        repo.attach_content_item_to_story.assert_called_once_with("story-2", "new")

    def test_candidate_window_is_passed_to_repository(self):
        published = datetime(2026, 1, 1)
        repo = self.repo()
        story = SimpleNamespace(id="story-1", last_updated_at=published)
        repo.create_story.return_value = story
        cluster_content_item(repo, self.item("new", "A title", published))
        repo.find_candidate_stories.assert_called_once_with(published, 48)

    def test_existing_association_is_idempotent(self):
        story_link = SimpleNamespace(story_id="story-1")
        item = self.item("new", "A title", datetime(2026, 1, 1))
        item.story_content = story_link
        story = SimpleNamespace(id="story-1")
        repo = self.repo()
        repo.get_story.side_effect = None
        repo.get_story.return_value = story
        self.assertIs(cluster_content_item(repo, item), story)
        repo.attach_content_item_to_story.assert_not_called()

    def test_duplicate_association_is_rejected_by_repository_contract(self):
        repo = Mock()
        repo.attach_content_item_to_story.side_effect = ValueError(
            "ContentItem is already associated with another Story"
        )
        with self.assertRaises(ValueError):
            repo.attach_content_item_to_story("story-2", "item-1")

    def test_failure_can_be_isolated_by_caller(self):
        repo = self.repo()
        repo.find_candidate_stories.side_effect = RuntimeError("candidate lookup failed")
        with self.assertRaises(RuntimeError):
            cluster_content_item(repo, self.item("new", "A title", datetime(2026, 1, 1)))


if __name__ == "__main__":
    unittest.main()
