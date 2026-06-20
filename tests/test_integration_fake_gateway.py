import asyncio
import time

from adtention_hermes.plugin import Runtime, on_pre_gateway_dispatch
from conftest import FakeGateway, fake_event


class SlowFakeClient:
    def __init__(self, delay_seconds=10):
        self.delay_seconds = delay_seconds
        self.serve_calls = []
        self.acks = []

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
    asyncio.run(gateway.adapters["telegram"].send("chat1", "⏳ Working — 3 min"))

    assert "Neon" in gateway.adapters["telegram"].sent[0][1]
    assert len(client.acks) == 1
    assert "chat_id" not in client.acks[0]
    assert "message" not in client.acks[0]


def test_no_cached_sponsor_leaves_wait_state_unchanged(tmp_path):
    client = FastFakeClient()
    runtime = Runtime.for_tests(base_dir=tmp_path, client=client, publisher_id="pub_1")
    gateway = FakeGateway()

    on_pre_gateway_dispatch(event=fake_event("Research AI papers"), gateway=gateway, runtime=runtime)
    asyncio.run(gateway.adapters["telegram"].send("chat1", "⏳ Working — 3 min"))

    assert gateway.adapters["telegram"].sent[0][1] == "⏳ Working — 3 min"


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
    asyncio.run(gateway.adapters["discord"].send("channel1", "⏳ Working — 3 min"))

    assert "ADtention" in gateway.adapters["discord"].sent[0][1]


def test_disabled_plugin_is_byte_for_byte_unchanged(tmp_path):
    client = FastFakeClient()
    runtime = Runtime.for_tests(base_dir=tmp_path, client=client, publisher_id="pub_1")
    runtime.state.set_enabled(False)
    runtime.state.save_sponsor(runtime.default_session_key, {"text": "Neon", "creative_id": "cr_1", "impression_id": "imp_1"})
    gateway = FakeGateway()

    on_pre_gateway_dispatch(event=fake_event("Research competitors"), gateway=gateway, runtime=runtime)
    asyncio.run(gateway.adapters["telegram"].send("chat1", "⏳ Working — 3 min"))

    assert gateway.adapters["telegram"].sent[0][1] == "⏳ Working — 3 min"
