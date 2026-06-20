"""Local-only task categorization for Hermes.

The classifier intentionally returns only broad categories. It does not retain
or serialize the user prompt, chat history, files, paths, or tool arguments.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

LEGACY_CATEGORIES = {"web3", "web", "devops", "data", "systems", "general"}
V2_CATEGORIES = {
    "coding",
    "devops",
    "data_ai",
    "web_research",
    "browser_scraping",
    "productivity",
    "creative_media",
    "github",
    "business_research",
    "web3",
    "smart_home",
    "general",
}

V2_TO_LEGACY = {
    "coding": "web",
    "devops": "devops",
    "data_ai": "data",
    "web_research": "data",
    "browser_scraping": "data",
    "productivity": "general",
    "creative_media": "general",
    "github": "devops",
    "business_research": "data",
    "web3": "web3",
    "smart_home": "general",
    "general": "general",
}

KEYWORDS = {
    "business_research": (
        "competitor", "competitors", "market", "pricing", "tam", "sam", "som",
        "leads", "lead", "publisher", "advertiser", "monetization", "revenue",
        "makeup", "foundation", "shade match", "findation", "matchmymakeup",
        "business model", "customer discovery",
    ),
    "browser_scraping": (
        "scrape", "scraping", "crawl", "crawler", "firecrawl", "browser", "playwright",
        "selenium", "extract product", "extract prices", "page snapshot", "website extraction",
    ),
    "web_research": (
        "research", "search", "sources", "citation", "summarize articles", "news",
        "blog", "monitor", "rss", "literature", "paper", "papers", "web search",
    ),
    "coding": (
        "code", "build", "implement", "bug", "tests", "pytest", "react", "tailwind",
        "typescript", "javascript", "python", "api", "plugin", "repo", "repository",
        "function", "class", "frontend", "backend",
    ),
    "devops": (
        "docker", "kubernetes", "k8s", "nginx", "deploy", "deployment", "server",
        "vps", "systemctl", "cron", "port", "ssl", "terraform", "ci/cd", "ingress",
    ),
    "data_ai": (
        "data", "dataset", "pandas", "embedding", "embeddings", "llm", "model",
        "fine-tune", "finetune", "train", "training", "gpu", "benchmark", "eval",
    ),
    "creative_media": (
        "image", "video", "audio", "song", "music", "illustration", "design", "logo",
        "hero image", "comic", "infographic", "render", "generate art",
    ),
    "github": (
        "github", "pull request", "pr", "issue", "commit", "branch", "release", "gh cli",
    ),
    "web3": (
        "crypto", "web3", "solidity", "ethereum", "solana", "token", "wallet", "defi",
        "smart contract", "nft",
    ),
    "smart_home": (
        "home assistant", "lights", "light", "thermostat", "hue", "kitchen", "bedroom",
        "living room", "turn on", "turn off", "smart home",
    ),
    "productivity": (
        "email", "calendar", "notion", "google doc", "docs", "sheets", "spreadsheet",
        "drive", "meeting", "slides", "powerpoint", "airtable",
    ),
}

TOOL_HINTS = {
    "browser_scraping": ("browser_navigate", "browser_snapshot", "browser_click", "browser_type", "browser_scroll"),
    "web_research": ("web_search", "web_extract", "x_search", "session_search"),
    "coding": ("read_file", "write_file", "patch", "search_files", "terminal"),
    "creative_media": ("image_generate", "video", "video_gen", "text_to_speech"),
    "productivity": ("send_message", "google", "notion", "airtable"),
    "smart_home": ("homeassistant", "openhue"),
    "devops": ("cronjob", "process", "terminal"),
}

# Tie-break order. More specific categories come first.
PRIORITY = (
    "business_research",
    "browser_scraping",
    "github",
    "web3",
    "smart_home",
    "creative_media",
    "devops",
    "data_ai",
    "coding",
    "productivity",
    "web_research",
    "general",
)


@dataclass(frozen=True)
class Classification:
    category: str
    category_v2: str
    source: str
    confidence: float

    def to_payload(self) -> dict[str, object]:
        return {
            "category": self.category,
            "category_v2": self.category_v2,
            "confidence": round(self.confidence, 3),
            "source": self.source,
        }


def _iter_texts(*values: str | None) -> Iterable[str]:
    for value in values:
        if value:
            yield str(value).lower()


def classify_turn(
    *,
    user_message: str = "",
    platform: str = "",
    chat_name: str = "",
    chat_topic: str = "",
    observed_tools: list[str] | None = None,
    media_types: list[str] | None = None,
) -> Classification:
    scores = {category: 0 for category in V2_CATEGORIES}
    haystack = "\n".join(_iter_texts(user_message, chat_name, chat_topic, platform))

    for category, keywords in KEYWORDS.items():
        for keyword in keywords:
            if keyword in haystack:
                scores[category] += 2 if " " in keyword else 1

    for tool in observed_tools or []:
        tool_l = str(tool).lower()
        for category, hints in TOOL_HINTS.items():
            if any(hint in tool_l for hint in hints):
                scores[category] += 2

    for media in media_types or []:
        media_l = str(media).lower()
        if media_l in {"photo", "image", "video", "audio", "voice"}:
            scores["creative_media"] += 1

    best = max(PRIORITY, key=lambda category: (scores.get(category, 0), -PRIORITY.index(category)))
    best_score = scores.get(best, 0)
    if best_score <= 0:
        best = "general"
        confidence = 0.0
        source = "fallback"
    else:
        confidence = min(0.95, 0.35 + best_score * 0.12)
        source = "local_keywords"

    return Classification(
        category=V2_TO_LEGACY[best],
        category_v2=best,
        source=source,
        confidence=confidence,
    )
