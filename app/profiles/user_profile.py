from typing import List

from pydantic import BaseModel, Field


class UserProfile(BaseModel):
    user_id: str = "default"
    preferred_topics: List[str] = Field(default_factory=list)
    preferred_entities: List[str] = Field(default_factory=list)
    excluded_topics: List[str] = Field(default_factory=list)
    excluded_entities: List[str] = Field(default_factory=list)
    preferred_content_types: List[str] = Field(default_factory=list)
    prefer_practical: bool = False
    prefer_technical_depth: bool = False


USER_PROFILE = {
    "name": "Dave",
    "title": "AI Engineer & Researcher",
    "background": "Experienced AI engineer with deep interest in practical AI applications, research breakthroughs, and production-ready systems",
    "interests": [
        "Large Language Models (LLMs) and their applications",
        "Retrieval-Augmented Generation (RAG) systems",
        "AI agent architectures and frameworks",
        "Multimodal AI and vision-language models",
        "AI safety and alignment research",
        "Production AI systems and MLOps",
        "Real-world AI applications and case studies",
        "Technical tutorials and implementation guides",
        "Research papers with practical implications",
        "AI infrastructure and scaling challenges"
    ],
    "preferences": {
        "prefer_practical": True,
        "prefer_technical_depth": True,
        "prefer_research_breakthroughs": True,
        "prefer_production_focus": True,
        "avoid_marketing_hype": True
    },
    "expertise_level": "Advanced"
}


def get_structured_user_profile(user_id: str = "default") -> UserProfile:
    """Adapt the legacy default profile to the typed ranking representation."""
    if user_id != "default":
        return UserProfile(user_id=user_id)
    return UserProfile(
        user_id=user_id,
        preferred_topics=USER_PROFILE["interests"],
        prefer_practical=USER_PROFILE["preferences"]["prefer_practical"],
        prefer_technical_depth=USER_PROFILE["preferences"]["prefer_technical_depth"],
    )

def get_user_profile(user_id: str = "default") -> dict:
    """
    Get the user profile. Currently returns a hardcoded profile.
    Future: Fetch from the database based on user_id.
    """
    return USER_PROFILE
