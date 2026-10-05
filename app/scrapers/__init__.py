from .base import registry
from .youtube import YouTubeScraper
from .openai import OpenAIScraper
from .anthropic import AnthropicScraper
from .rss_generic import GenericRSSScraper
from .arxiv import ArxivScraper
from .hacker_news import HackerNewsScraper

# Guard: only register once even if this module is imported multiple times.
if not registry.get_all():
    # Existing Phase 1 & 2 sources
    registry.register(YouTubeScraper())
    registry.register(OpenAIScraper())
    registry.register(AnthropicScraper())

    # Phase 3 sources (all use official RSS or public APIs — no credentials required)
    registry.register(GenericRSSScraper(
        name="Hugging Face",
        rss_url="https://huggingface.co/blog/feed.xml"
    ))
    registry.register(GenericRSSScraper(
        name="NVIDIA AI",
        rss_url="https://developer.nvidia.com/blog/feed/"
    ))
    registry.register(GenericRSSScraper(
        name="Microsoft AI",
        rss_url="https://www.microsoft.com/en-us/research/blog/feed/"
    ))
    registry.register(ArxivScraper())
    registry.register(HackerNewsScraper())

