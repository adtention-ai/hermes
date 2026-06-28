import asyncio
import time

from adtention_hermes.plugin import Runtime, on_pre_gateway_dispatch
from conftest import FakeGateway, fake_event


class SlowFakeClient:
    def __init__(self, delay_seconds=10):
        self.delay_seconds = delay_seconds
        self.register_calls = []
        self.serve_calls = []
        self.acks = []

    def register_install(self, **kwargs):
        self.register_calls.append(kwargs)
        return {"publisher_id": "pub_registered"}

    def serve(self, **kwargs):
        self.serve_calls.append(kwargs)
        time.sleep(self.delay_seconds)
        return {
            "text": "Neon: Postgres for AI agents",
            "creative_id": "cr_1",
            "impression_id": "imp_1",
            "click_url": "https://api.adtention.ai/v1/click/imp_1",
            "balance_usd": 0.42,
        }

    def ack_rendered(self, **kwargs):
        self.acks.append(kwargs)
        return {"ok": True}


class FastFakeClient(SlowFakeClient):
    def __init__(self):
        super().__init__(delay_seconds=0)


def test_pre_gateway_dispatch_prefetches_sponsor_without_blocking(tmp_path):
    client = SlowFakeClient(delay_seconds=2)
    runtime = Runtime.for_tests(base_dir=tmp_path, client=client, publisher_id="pub_1")
    gateway = FakeGateway()

    start = time.monotonic()
    on_pre_gateway_dispatch(event=fake_event("Research AI papers"), gateway=gateway, runtime=runtime)
    elapsed = time.monotonic() - start

    assert elapsed < 0.25


def test_wait_state_uses_cached_sponsor_and_acks_after_send(tmp_path):
    client = FastFakeClient()
    runtime = Runtime.for_tests(base_dir=tmp_path, client=client, publisher_id="pub_1")
    runtime.state.save_sponsor(runtime.default_session_key, {
        "text": "Neon: Postgres for AI agents",
        "creative_id": "cr_1",
        "impression_id": "imp_1",
        "click_url": "https://api.adtention.ai/v1/click/imp_1",
        "balance_usd": 0.42,
    })
    gateway = FakeGateway()

    on_pre_gateway_dispatch(event=fake_event("Research AI papers"), gateway=gateway, runtime=runtime)
    asyncio.run(gateway.adapters["telegram"].send_or_update_status("chat1", "lifecycle", "⏳ Working — 3 min"))

    sent_text = gateway.adapters["telegram"].status_updates[0][1]
    assert "**Neon: Postgres for AI agents**" in sent_text
    assert "$0.42" in sent_text
    assert "[More Info](https://api.adtention.ai/v1/click/imp_1)" in sent_text
    assert "ADtention" not in sent_text
    assert len(client.acks) == 1
    assert "chat_id" not in client.acks[0]
    assert "message" not in client.acks[0]


def test_render_ack_consumes_cached_sponsor(tmp_path):
    client = FastFakeClient()
    runtime = Runtime.for_tests(base_dir=tmp_path, client=client, publisher_id="pub_1")
    runtime.state.save_sponsor(runtime.default_session_key, {
        "text": "Neon: Postgres for AI agents",
        "creative_id": "cr_1",
        "impression_id": "imp_1",
        "click_url": "https://api.adtention.ai/v1/click/imp_1",
        "balance_usd": 0.42,
    })
    gateway = FakeGateway()

    on_pre_gateway_dispatch(event=fake_event("Research AI papers"), gateway=gateway, runtime=runtime)
    asyncio.run(gateway.adapters["telegram"].send_or_update_status("chat1", "lifecycle", "⏳ Working — 3 min"))

    assert len(client.acks) == 1
    assert runtime.state.get_sponsor(runtime.default_session_key) is None


def test_duplicate_cached_impression_is_not_re_rendered(tmp_path):
    client = FastFakeClient()
    runtime = Runtime.for_tests(base_dir=tmp_path, client=client, publisher_id="pub_1")
    gateway = FakeGateway()
    sponsor = {
        "text": "Neon: Postgres for AI agents",
        "creative_id": "cr_1",
        "impression_id": "imp_1",
        "click_url": "https://api.adtention.ai/v1/click/imp_1",
        "balance_usd": 0.42,
    }

    on_pre_gateway_dispatch(event=fake_event("Research AI papers"), gateway=gateway, runtime=runtime)
    runtime.state.save_sponsor(runtime.default_session_key, sponsor)
    asyncio.run(gateway.adapters["telegram"].send_or_update_status("chat1", "lifecycle", "⏳ Working — 3 min"))
    runtime.state.save_sponsor(runtime.default_session_key, sponsor)
    asyncio.run(gateway.adapters["telegram"].send_or_update_status(
        "chat1",
        "compression",
        "⏳ Working — compressing",
        metadata={"adtention_render_scope": "turn-b"},
    ))

    assert len(client.acks) == 1
    assert runtime.state.get_sponsor(runtime.default_session_key) is None
    assert "Neon" not in gateway.adapters["telegram"].status_updates[-1][1]


def test_one_render_per_gateway_turn_even_with_new_cached_sponsor(tmp_path):
    client = FastFakeClient()
    runtime = Runtime.for_tests(base_dir=tmp_path, client=client, publisher_id="pub_1")
    runtime.state.save_sponsor(runtime.default_session_key, {
        "text": "Neon",
        "creative_id": "cr_1",
        "impression_id": "imp_1",
        "click_url": "https://x/1",
        "balance_usd": 0.42,
    })
    gateway = FakeGateway()

    on_pre_gateway_dispatch(event=fake_event("Research AI papers"), gateway=gateway, runtime=runtime)
    asyncio.run(gateway.adapters["telegram"].send_or_update_status("chat1", "lifecycle", "⏳ Working — 3 min"))
    runtime.state.save_sponsor(runtime.default_session_key, {
        "text": "Linear",
        "creative_id": "cr_2",
        "impression_id": "imp_2",
        "click_url": "https://x/2",
        "balance_usd": 0.84,
    })
    asyncio.run(gateway.adapters["telegram"].send_or_update_status("chat1", "compression", "⏳ Working — compressing"))

    assert len(client.acks) == 1
    assert "Linear" not in gateway.adapters["telegram"].status_updates[-1][1]


def test_overlapping_gateway_turn_does_not_reset_prior_turn_render_cap(tmp_path):
    client = FastFakeClient()
    runtime = Runtime.for_tests(base_dir=tmp_path, client=client, publisher_id="pub_1")
    gateway = FakeGateway()

    on_pre_gateway_dispatch(event=fake_event("Research AI papers"), gateway=gateway, runtime=runtime)
    runtime.state.save_sponsor(runtime.default_session_key, {
        "text": "Neon",
        "creative_id": "cr_1",
        "impression_id": "imp_1",
        "click_url": "https://x/1",
        "balance_usd": 0.42,
    })
    asyncio.run(gateway.adapters["telegram"].send_or_update_status(
        "chat1",
        "lifecycle",
        "⏳ Working — 3 min",
        metadata={"adtention_render_scope": "turn-a"},
    ))

    on_pre_gateway_dispatch(event=fake_event("Summarize this PDF"), gateway=gateway, runtime=runtime)
    runtime.state.save_sponsor(runtime.default_session_key, {
        "text": "Linear",
        "creative_id": "cr_2",
        "impression_id": "imp_2",
        "click_url": "https://x/2",
        "balance_usd": 0.84,
    })
    asyncio.run(gateway.adapters["telegram"].send_or_update_status(
        "chat1",
        "compression",
        "⏳ Working — compressing",
        metadata={"adtention_render_scope": "turn-a"},
    ))

    assert len(client.acks) == 1
    assert "Linear" not in gateway.adapters["telegram"].status_updates[-1][1]


def test_no_cached_sponsor_leaves_wait_state_unchanged(tmp_path):
    client = FastFakeClient()
    runtime = Runtime.for_tests(base_dir=tmp_path, client=client, publisher_id="pub_1")
    gateway = FakeGateway()

    on_pre_gateway_dispatch(event=fake_event("Research AI papers"), gateway=gateway, runtime=runtime)
    asyncio.run(gateway.adapters["telegram"].send("chat1", "⏳ Working — 3 min"))

    assert gateway.adapters["telegram"].sent[0][1] == "⏳ Working — 3 min"


def test_prefetch_registers_install_when_publisher_id_missing(tmp_path):
    client = FastFakeClient()
    runtime = Runtime.for_tests(base_dir=tmp_path, client=client, publisher_id=None)

    classification = runtime.classify_and_store(runtime.default_session_key, user_message="Research AI papers")
    runtime.prefetch_sponsor_async(runtime.default_session_key, classification, "telegram")

    deadline = time.monotonic() + 1
    while time.monotonic() < deadline and not client.serve_calls:
        time.sleep(0.01)

    assert client.register_calls == [{"install_id": runtime.install_id}]
    assert client.serve_calls[0]["publisher_id"] == "pub_registered"
    assert runtime.publisher_id == "pub_registered"
    assert runtime.state.get_publisher_id() == "pub_registered"


def test_final_answer_after_same_turn_is_not_decorated(tmp_path):
    client = FastFakeClient()
    runtime = Runtime.for_tests(base_dir=tmp_path, client=client, publisher_id="pub_1")
    runtime.state.save_sponsor(runtime.default_session_key, {
        "text": "Neon",
        "creative_id": "cr_1",
        "impression_id": "imp_1",
        "click_url": "https://x",
        "balance_usd": 0.42,
    })
    gateway = FakeGateway()

    on_pre_gateway_dispatch(event=fake_event("Research competitors"), gateway=gateway, runtime=runtime)
    asyncio.run(gateway.adapters["telegram"].send("chat1", "Final answer: here are the competitors."))

    assert "ADtention" not in gateway.adapters["telegram"].sent[0][1]


def test_discord_adapter_gets_same_behavior(tmp_path):
    client = FastFakeClient()
    runtime = Runtime.for_tests(base_dir=tmp_path, client=client, publisher_id="pub_1")
    runtime.state.save_sponsor(runtime.default_session_key, {
        "text": "Neon",
        "creative_id": "cr_1",
        "impression_id": "imp_1",
        "click_url": "https://x",
        "balance_usd": 0.42,
    })
    gateway = FakeGateway(platforms=("discord",))

    on_pre_gateway_dispatch(event=fake_event("Scrape this website", platform="discord"), gateway=gateway, runtime=runtime)
    asyncio.run(gateway.adapters["discord"].send("channel1", "⏳ Working — 3 min", metadata={"non_conversational": True}))

    sent_text = gateway.adapters["discord"].sent[0][1]
    assert "ADtention" not in sent_text
    assert "**Neon**" in sent_text
    assert "[More Info](https://x)" in sent_text


def test_disabled_plugin_is_byte_for_byte_unchanged(tmp_path):
    client = FastFakeClient()
    runtime = Runtime.for_tests(base_dir=tmp_path, client=client, publisher_id="pub_1")
    runtime.state.set_enabled(False)
    runtime.state.save_sponsor(runtime.default_session_key, {"text": "Neon", "creative_id": "cr_1", "impression_id": "imp_1"})
    gateway = FakeGateway()

    on_pre_gateway_dispatch(event=fake_event("Research competitors"), gateway=gateway, runtime=runtime)
    asyncio.run(gateway.adapters["telegram"].send("chat1", "⏳ Working — 3 min"))

    assert gateway.adapters["telegram"].sent[0][1] == "⏳ Working — 3 min"
