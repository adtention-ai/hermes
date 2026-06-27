from adtention_hermes.renderer import (
    SPONSOR_MARKER,
    append_sponsor_segment,
    decorate_wait_state,
    is_wait_state,
    strip_existing_segment,
)

SPONSOR = {
    "text": "Neon: Postgres for AI agents",
    "creative_id": "cr_1",
    "impression_id": "imp_1",
    "click_url": "https://api.adtention.ai/v1/click/imp_1",
    "balance_usd": 0.42,
}


def test_detects_hermes_working_heartbeat():
    assert is_wait_state("⏳ Working — 3 min") is True


def test_tool_progress_is_not_billable_wait_state():
    assert is_wait_state("Running tool web_search") is False
    assert decorate_wait_state("Tool progress: web_search", SPONSOR, max_chars=500) == "Tool progress: web_search"


def test_does_not_treat_final_answer_as_wait_state():
    assert is_wait_state("Here is the final answer to your question.") is False


def test_appends_sponsor_segment_to_wait_state():
    result = append_sponsor_segment("⏳ Working — 3 min", SPONSOR, max_chars=500)
    assert "⏳ Working — 3 min" in result
    assert "⊕" not in result
    assert "ADtention" not in result
    assert "$0.42" in result
    assert SPONSOR_MARKER in result
    assert "**Neon: Postgres for AI agents**" in result
    assert "→ [More Info](https://api.adtention.ai/v1/click/imp_1)" in result


def test_decorate_wait_state_leaves_unknown_messages_unchanged():
    text = "Here is the final answer."
    assert decorate_wait_state(text, SPONSOR, max_chars=500) == text


def test_replaces_existing_sponsor_segment_on_edit():
    first = append_sponsor_segment("⏳ Working — 3 min", SPONSOR, max_chars=500)
    updated = first.replace("3 min", "4 min")
    new_sponsor = dict(SPONSOR, text="Linear: Issue tracking for AI teams", impression_id="imp_2")

    second = append_sponsor_segment(updated, new_sponsor, max_chars=500)

    assert second.count(SPONSOR_MARKER) == 1
    assert "**Linear: Issue tracking" in second
    assert "Neon: Postgres" not in second
    assert "⏳ Working — 4 min" in second


def test_replaces_current_segment_without_balance_on_edit():
    sponsor = {"text": "Neon", "click_url": "https://x"}
    first = append_sponsor_segment("⏳ Working — 3 min", sponsor, max_chars=500)
    second = append_sponsor_segment(first.replace("3 min", "4 min"), sponsor, max_chars=500)

    assert second.count("**Neon**") == 1
    assert second.count(SPONSOR_MARKER) == 1
    assert "⏳ Working — 4 min" in second


def test_replaces_current_segment_with_nonstandard_balance_on_edit():
    sponsor = {"text": "Neon", "balance_display": "42 credits", "click_url": "https://x"}
    first = append_sponsor_segment("⏳ Working — 3 min", sponsor, max_chars=500)
    second = append_sponsor_segment(first.replace("3 min", "4 min"), sponsor, max_chars=500)

    assert second.count("42 credits · **Neon**") == 1
    assert second.count(SPONSOR_MARKER) == 1
    assert "⏳ Working — 4 min" in second


def test_escapes_markdown_inside_balance_display():
    sponsor = {"text": "Neon", "balance_display": "[paid]", "click_url": "https://x"}
    result = append_sponsor_segment("⏳ Working — 3 min", sponsor, max_chars=500)
    assert "\\[paid\\] · **Neon**" in result


def test_incomplete_sponsor_without_click_url_is_not_rendered():
    sponsor = {"text": "Neon"}
    assert append_sponsor_segment("⏳ Working — 3 min", sponsor, max_chars=500) == "⏳ Working — 3 min"


def test_strip_existing_sponsor_segment_removes_legacy_plugin_line():
    text = "⏳ Working — 3 min\nregular progress line\n⊕ ADtention · Old Sponsor"
    stripped = strip_existing_segment(text)
    assert "regular progress line" in stripped
    assert "ADtention" not in stripped


def test_strip_existing_sponsor_segment_removes_current_plugin_line():
    text = f"⏳ Working — 3 min\nregular progress line\n{SPONSOR_MARKER}$0.42 · **Old Sponsor** → [More Info](https://x)"
    stripped = strip_existing_segment(text)
    assert "regular progress line" in stripped
    assert "Old Sponsor" not in stripped
    assert SPONSOR_MARKER not in stripped


def test_strip_existing_segment_preserves_non_plugin_more_info_line():
    text = "⏳ Working — 3 min\nDocs: [More Info](https://example.com)"
    stripped = strip_existing_segment(text)
    assert "Docs: [More Info](https://example.com)" in stripped


def test_strip_existing_segment_preserves_unmarked_sponsor_shaped_line():
    text = "⏳ Working — 3 min\n$0.42 · **Not ADtention** → [More Info](https://example.com)"
    stripped = strip_existing_segment(text)
    assert "$0.42 · **Not ADtention** → [More Info](https://example.com)" in stripped


def test_sanitizes_control_characters_and_newlines():
    sponsor = dict(SPONSOR, text="Bad\x1b[31mAd\nNext line")
    result = append_sponsor_segment("⏳ Working — 3 min", sponsor, max_chars=500)
    segment = result.splitlines()[-1]
    assert "\x1b" not in segment
    assert "\nNext line" not in segment
    assert "**Bad\\[31mAd Next line**" in segment


def test_escapes_markdown_inside_bold_ad_text():
    sponsor = dict(SPONSOR, text="ACME_[agent](test) *deal*")
    result = append_sponsor_segment("⏳ Working — 3 min", sponsor, max_chars=500)
    assert "**ACME\\_\\[agent\\]\\(test\\) \\*deal\\***" in result


def test_respects_length_limit():
    sponsor = dict(SPONSOR, text="x" * 1000)
    result = append_sponsor_segment("⏳ Working — 3 min", sponsor, max_chars=120)
    assert len(result) <= 120
    assert result.startswith("⏳ Working")
