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


def test_saves_and_reads_referral_identity(tmp_path):
    store = StateStore(tmp_path)

    store.set_referral(referral_code="h3r7vmj", referral_url="https://adtention.ai/r/h3r7vmj")

    assert store.get_referral_code() == "h3r7vmj"
    assert store.get_referral_url() == "https://adtention.ai/r/h3r7vmj"
    assert store.get_referral() == {
        "referral_code": "h3r7vmj",
        "referral_url": "https://adtention.ai/r/h3r7vmj",
    }


def test_render_dedupe_by_impression_even_across_messages(tmp_path):
    store = StateStore(tmp_path)
    assert store.mark_rendered_once(("imp_1", "cr_1", "telegram", "msg_1")) is True
    assert store.mark_rendered_once(("imp_1", "cr_1", "telegram", "msg_2")) is False
    assert store.mark_rendered_once(("imp_2", "cr_1", "telegram", "msg_2")) is True


def test_consume_sponsor_removes_cached_impression(tmp_path):
    store = StateStore(tmp_path)
    store.save_sponsor("s1", {"creative_id": "cr_1", "impression_id": "imp_1", "text": "Neon"})

    store.consume_sponsor("s1", "imp_1")

    assert store.get_sponsor("s1") is None


def test_sponsor_cache_respects_ttl(tmp_path):
    store = StateStore(tmp_path)
    store.save_sponsor("s1", {"creative_id": "cr_1", "impression_id": "imp_1", "text": "Neon"}, now=1000)

    assert store.get_sponsor("s1", max_age_seconds=60, now=1059)["impression_id"] == "imp_1"
    assert store.get_sponsor("s1", max_age_seconds=60, now=1061) is None


def test_render_scope_caps_one_impression_per_turn(tmp_path):
    store = StateStore(tmp_path)
    store.begin_render_scope("turn_1")

    assert store.can_render_in_current_scope() is True
    store.mark_current_scope_rendered()
    assert store.can_render_in_current_scope() is False
    store.begin_render_scope("turn_2")
    assert store.can_render_in_current_scope() is True


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


def test_corrupt_database_is_quarantined_and_recreated(tmp_path):
    db_path = tmp_path / "adtention.sqlite3"
    db_path.write_bytes(b"SQLit\x17\x03\x03not-a-sqlite-db")

    store = StateStore(tmp_path)

    assert store.get_or_create_install_id().startswith("hermes_")
    assert db_path.read_bytes().startswith(b"SQLite format 3\x00")
    backups = list(tmp_path.glob("adtention.sqlite3.corrupt-*.bak"))
    assert len(backups) == 1
    assert backups[0].read_bytes().startswith(b"SQLit\x17\x03\x03")
