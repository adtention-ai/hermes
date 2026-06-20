import asyncio

from adtention_hermes.gateway_patch import wrap_adapter, wrap_gateway
from adtention_hermes.renderer import SPONSOR_MARKER
from conftest import BrokenRuntime, FailingAdapter, FakeAdapter, FakeGateway, FakeRuntime


class EnumLikePlatform:
    value = "telegram"

    def __str__(self):
        return "Platform.TELEGRAM"


def test_wraps_adapter_once():
    adapter = FakeAdapter()
    runtime = FakeRuntime()
    wrap_adapter(adapter, runtime)
    first_send = adapter.send
    wrap_adapter(adapter, runtime)
    assert adapter.send is first_send


def test_wrap_gateway_wraps_all_supported_adapters():
    gateway = FakeGateway(platforms=("telegram", "discord"))
    runtime = FakeRuntime()
    wrap_gateway(gateway, runtime)
    assert gateway.adapters["telegram"]._adtention_wrapped is True
    assert gateway.adapters["discord"]._adtention_wrapped is True


def test_send_decorates_wait_state():
    adapter = FakeAdapter()
    runtime = FakeRuntime()
    wrap_adapter(adapter, runtime)

    result = asyncio.run(adapter.send("chat1", "⏳ Working — 3 min"))

    sent_text = adapter.sent[0][1]
    assert "⏳ Working — 3 min" in sent_text
    assert "Neon" in sent_text
    assert SPONSOR_MARKER in sent_text
    assert result.success is True


def test_send_does_not_decorate_unsupported_platform():
    adapter = FakeAdapter(platform="slack")
    runtime = FakeRuntime()
    wrap_adapter(adapter, runtime)

    asyncio.run(adapter.send("chat1", "⏳ Working — 3 min"))

    assert "Neon" not in adapter.sent[0][1]
    assert runtime.acked == []


def test_ack_uses_platform_enum_value_not_repr():
    adapter = FakeAdapter(platform=EnumLikePlatform())
    runtime = FakeRuntime()
    wrap_adapter(adapter, runtime)

    asyncio.run(adapter.send("chat1", "⏳ Working — 3 min"))

    assert runtime.acked[0]["platform"] == "telegram"


def test_send_does_not_decorate_final_answer():
    adapter = FakeAdapter()
    runtime = FakeRuntime()
    wrap_adapter(adapter, runtime)

    asyncio.run(adapter.send("chat1", "Here is the final answer."))

    assert "Neon" not in adapter.sent[0][1]


def test_send_decorates_real_hermes_content_keyword():
    adapter = FakeAdapter()
    runtime = FakeRuntime()
    wrap_adapter(adapter, runtime)

    asyncio.run(adapter.send("chat1", text="ignored by fake", content="⏳ Working — 3 min"))

    sent_kwargs = adapter.sent[0][2]
    assert "Neon" in sent_kwargs["content"]


def test_status_update_decorates_real_telegram_content_position():
    adapter = FakeAdapter()
    runtime = FakeRuntime()
    wrap_adapter(adapter, runtime)

    asyncio.run(adapter.send_or_update_status("chat1", "lifecycle", "⏳ Working — 3 min"))

    assert "Neon" in adapter.status_updates[0][1] or "Neon" in adapter.status_updates[0][2].get("content", "")


def test_edit_decorates_real_hermes_content_keyword():
    adapter = FakeAdapter()
    runtime = FakeRuntime()
    wrap_adapter(adapter, runtime)

    asyncio.run(adapter.edit_message("chat1", "m1", text="ignored by fake", content="⏳ Working — 3 min"))

    assert "Neon" in adapter.edited[0][3]["content"]


def test_edit_replaces_existing_segment_not_duplicate():
    adapter = FakeAdapter()
    runtime = FakeRuntime()
    wrap_adapter(adapter, runtime)

    asyncio.run(adapter.edit_message("chat1", "m1", "⏳ Working — 3 min\n⊕ ADtention · Old"))
    text = adapter.edited[0][2]

    assert text.count(SPONSOR_MARKER) == 1
    assert "Neon" in text


def test_failed_send_does_not_ack_impression():
    adapter = FailingAdapter()
    runtime = FakeRuntime()
    wrap_adapter(adapter, runtime)

    asyncio.run(adapter.send("chat1", "⏳ Working — 3 min"))

    assert runtime.acked == []


def test_successful_send_and_edit_ack_once_for_same_message():
    adapter = FakeAdapter()
    runtime = FakeRuntime()
    wrap_adapter(adapter, runtime)

    asyncio.run(adapter.send("chat1", "⏳ Working — 3 min"))
    asyncio.run(adapter.edit_message("chat1", "m1", "⏳ Working — 4 min"))

    assert len(runtime.acked) == 1


def test_disabled_runtime_leaves_wait_state_unchanged():
    adapter = FakeAdapter()
    runtime = FakeRuntime(enabled=False)
    wrap_adapter(adapter, runtime)

    asyncio.run(adapter.send("chat1", "⏳ Working — 3 min"))

    assert adapter.sent[0][1] == "⏳ Working — 3 min"


def test_wrapper_exception_falls_back_to_original_send():
    adapter = FakeAdapter()
    runtime = BrokenRuntime()
    wrap_adapter(adapter, runtime)

    asyncio.run(adapter.send("chat1", "⏳ Working — 3 min"))

    assert adapter.sent[0][1] == "⏳ Working — 3 min"
    assert runtime.acked == []
