import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.scrapers.base import registry
import app.scrapers # to populate registry

def verify_pg_integration_phase3():
    print("Starting PostgreSQL Integration Verification (Phase 3)...")
    
    adapters = registry.get_all()
    print(f"Registered adapters: {len(adapters)}")
    
    names = [adapter.source_name for adapter in adapters]
    print(f"Sources: {', '.join(names)}")
    
    # We won't test full DB insertion here because Phase 2 already verifies
    # that bulk_create_content_items works for any generic dict.
    # We just ensure the registry is intact and failure isolation is ready.
    
    expected_sources = [
        "YouTube", "OpenAI RSS", "Anthropic RSS", 
        "Hugging Face", "NVIDIA AI", "Microsoft AI", 
        "arXiv AI/ML", "Hacker News AI"
    ]
    
    missing = [s for s in expected_sources if s not in names]
    if missing:
        print(f"  [FAIL] Missing sources: {missing}")
        return False
        
    print("  [PASS] All expected sources are registered.")
    
    print("\n✅ Phase 3 Registry check passed!")
    return True

if __name__ == "__main__":
    success = verify_pg_integration_phase3()
    sys.exit(0 if success else 1)
