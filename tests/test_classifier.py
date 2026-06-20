from adtention_hermes.classifier import classify_turn


def test_classifies_makeup_competitor_research_as_business_research():
    result = classify_turn(user_message="Research foundation shade matching competitors like Findation")
    assert result.category_v2 == "business_research"
    assert result.category == "data"


def test_classifies_scraping_task_as_browser_scraping():
    result = classify_turn(user_message="Scrape this site and extract product prices")
    assert result.category_v2 == "browser_scraping"
    assert result.category == "data"


def test_classifies_firecrawl_browser_task_as_browser_scraping():
    result = classify_turn(user_message="Use Firecrawl browser to scrape these pages")
    assert result.category_v2 == "browser_scraping"


def test_classifies_react_task_as_coding():
    result = classify_turn(user_message="Build a React landing page with Tailwind")
    assert result.category_v2 == "coding"
    assert result.category == "web"


def test_classifies_kubernetes_task_as_devops():
    result = classify_turn(user_message="Debug my Kubernetes deployment and nginx ingress")
    assert result.category_v2 == "devops"


def test_classifies_image_generation_as_creative_media():
    result = classify_turn(user_message="Generate a product hero image")
    assert result.category_v2 == "creative_media"


def test_classifies_home_assistant_as_smart_home():
    result = classify_turn(user_message="Turn on the kitchen lights with Home Assistant")
    assert result.category_v2 == "smart_home"


def test_tool_usage_can_refine_category_to_web_research():
    result = classify_turn(user_message="Help me with this", observed_tools=["web_search", "web_extract"])
    assert result.category_v2 == "web_research"


def test_browser_tool_usage_can_refine_category_to_browser_scraping():
    result = classify_turn(user_message="Help me with this", observed_tools=["browser_navigate", "browser_snapshot"])
    assert result.category_v2 == "browser_scraping"


def test_classifier_never_returns_raw_prompt_in_serialized_payload():
    result = classify_turn(user_message="SECRET private project about Acme and internal pricing")
    payload = result.to_payload()
    assert "SECRET" not in repr(payload)
    assert "Acme" not in repr(payload)
    assert set(payload) == {"category", "category_v2", "confidence", "source"}
