import sys
from pathlib import Path
from datetime import datetime, timezone

# Ensure project root is on the path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database.repository import Repository
from app.database.models import ContentItem, Source

def verify_pg_integration():
    print("Starting PostgreSQL Integration Verification...")
    repo = Repository()
    
    test_external_id = "test-pg-integration-001"
    
    # 1. Cleanup any existing test data from previous runs
    existing_item = repo.session.query(ContentItem).filter_by(external_id=test_external_id).first()
    if existing_item:
        repo.session.delete(existing_item)
        repo.session.commit()
        print("  [INFO] Cleaned up existing test data.")

    # 2. Create test ContentItem
    print("  [STEP] Creating test ContentItem...")
    item = repo.create_content_item(
        source_name="PG Test Source",
        source_type="test",
        external_id=test_external_id,
        content_type="article",
        title="PostgreSQL Integration Test",
        url="http://test.local",
        published_at=datetime.now(timezone.utc),
        description="A test item to verify PostgreSQL integration."
    )
    
    if item is None:
        print("  [FAIL] Failed to create ContentItem (returned None)")
        return False
    print(f"  [PASS] ContentItem created successfully (ID: {item.id})")

    # 3. Read it back
    print("  [STEP] Reading ContentItem back from database...")
    # Using a fresh query to ensure it's in the DB
    read_item = repo.session.query(ContentItem).filter_by(external_id=test_external_id).first()
    
    if read_item is None:
        print("  [FAIL] Could not find the ContentItem in the database.")
        return False
        
    if read_item.title != "PostgreSQL Integration Test":
        print(f"  [FAIL] Title mismatch: Expected 'PostgreSQL Integration Test', got '{read_item.title}'")
        return False
        
    print("  [PASS] Read-back succeeded. Fields match.")

    # 4. Verify duplicate handling
    print("  [STEP] Testing duplicate external_id handling...")
    duplicate_item = repo.create_content_item(
        source_name="PG Test Source",
        source_type="test",
        external_id=test_external_id,
        content_type="article",
        title="Duplicate Title Attempt",
        url="http://test.local/dup",
        published_at=datetime.now(timezone.utc)
    )
    
    if duplicate_item is not None:
        print("  [FAIL] Duplicate insertion did not return None.")
        return False
        
    # Verify title wasn't overwritten
    check_item = repo.session.query(ContentItem).filter_by(external_id=test_external_id).first()
    if check_item.title != "PostgreSQL Integration Test":
        print(f"  [FAIL] Duplicate insertion overwrote existing data. Title is now: {check_item.title}")
        return False
        
    print("  [PASS] Duplicate handling succeeded (ignored gracefully).")

    # 5. Cleanup
    print("  [STEP] Cleaning up test records...")
    repo.session.delete(read_item)
    repo.session.commit()
    
    final_check = repo.session.query(ContentItem).filter_by(external_id=test_external_id).first()
    if final_check is not None:
        print("  [FAIL] Cleanup failed. Item still exists.")
        return False
        
    print("  [PASS] Cleanup succeeded. Database is clean of test data.")
    
    print("\n✅ All PostgreSQL integration checks passed successfully!")
    return True

if __name__ == "__main__":
    success = verify_pg_integration()
    sys.exit(0 if success else 1)
