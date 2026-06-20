from adtention_hermes.state import StateStore


def test_generates_stable_install_id(tmp_path):
    store = StateStore(tmp_path)
    first = store.get_or_create_install_id()
    second = store.get_or_create_install_id()
    assert first == second
    assert first.startswith("hermes_")


def test_saves_and_reads_sponsor_cache(tmp_path):
    store = StateStore(tmp_path)
    store.save_sponsor("s1", {"creative_id": "cr_1", "text": "Neon"})
    assert store.get_sponsor("s1")["creative_id"] == "cr_1"


def test_opt_out_disables_rendering(tmp_path):
    store = StateStore(tmp_path)
    store.set_enabled(False)
    assert store.is_enabled() is False
    store.set_enabled(True)
    assert store.is_enabled() is True


def test_render_dedupe_by_creative_platform_message(tmp_path):
    store = StateStore(tmp_path)
    key = ("cr_1", "telegram", "msg_1")
    assert store.mark_rendered_once(key) is True
    assert store.mark_rendered_once(key) is False


def test_frequency_cap_blocks_fast_refreshes(tmp_path):
    store = StateStore(tmp_path)
    assert store.can_refresh_sponsor(now=1000, min_seconds=15) is True
    store.mark_refreshed(now=1000)
    assert store.can_refresh_sponsor(now=1010, min_seconds=15) is False
    assert store.can_refresh_sponsor(now=1016, min_seconds=15) is True


def test_records_tool_names_without_arguments(tmp_path):
    store = StateStore(tmp_path)
    store.record_tool("s1", "web_search")
    store.record_tool("s1", "browser_navigate")
    assert store.get_observed_tools("s1") == ["web_search", "browser_navigate"]
    assert "secret query" not in repr(store.dump_debug())
