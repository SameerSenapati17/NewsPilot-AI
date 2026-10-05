import sys
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database.repository import Repository
from app.database.models import ContentItem
from app.normalizer import normalize
from app.scrapers.youtube import ChannelVideo

def verify_pg_integration_phase2():
    print("Starting PostgreSQL Integration Verification (Phase 2)...")
    repo = Repository()
    
    test_video_id = "test-phase2-vid-001"
    
    # 1. Cleanup
    existing = repo.session.query(ContentItem).filter_by(external_id=test_video_id).first()
    if existing:
        repo.session.delete(existing)
        repo.session.commit()

    # 2. Create normalized item
    video = ChannelVideo(
        title="Phase 2 Integration Test",
        url="http://youtube.com/test",
        video_id=test_video_id,
        published_at=datetime.now(timezone.utc),
        description="Testing normalization."
    )
    
    item_dict = normalize(video)
    
    # 3. Bulk insert
    inserted_count = repo.bulk_create_content_items("YouTube", "youtube", [item_dict])
    if inserted_count != 1:
        print("  [FAIL] Failed to bulk insert normalized item.")
        return False
        
    print("  [PASS] Normalized item inserted successfully.")
    
    # 4. Verify fields
    read_item = repo.session.query(ContentItem).filter_by(external_id=test_video_id).first()
    if not read_item or read_item.title != "Phase 2 Integration Test":
        print("  [FAIL] Title mismatch or item not found.")
        return False
        
    print("  [PASS] Read-back succeeded. Fields match.")
    
    # 5. Duplicate handling
    dup_count = repo.bulk_create_content_items("YouTube", "youtube", [item_dict])
    if dup_count != 0:
        print("  [FAIL] Duplicate insertion did not return 0.")
        return False
        
    print("  [PASS] Duplicate handling succeeded (ignored gracefully).")
    
    # 6. Cleanup
    repo.session.delete(read_item)
    repo.session.commit()
    print("  [PASS] Cleanup succeeded.")
    
    print("\n✅ All Phase 2 PostgreSQL integration checks passed!")
    return True

if __name__ == "__main__":
    success = verify_pg_integration_phase2()
    sys.exit(0 if success else 1)
