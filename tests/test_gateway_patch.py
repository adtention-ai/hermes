import asyncio
import importlib

from adtention_hermes.gateway_patch import patch_gateway_status_helper, wrap_adapter, wrap_gateway
from adtention_hermes.renderer import SPONSOR_MARKER
from conftest import BrokenRuntime, FailingAdapter, FakeAdapter, FakeGateway, FakeResult, FakeRuntime, FakeSource


class EnumLikePlatform:
    value = "telegram"

    def __str__(self):
        return "Platform.TELEGRAM"


class LegacyTelegramAdapter:
    platform = "telegram"

    def __init__(self):
        self.edited = []

    async def edit_message(self, chat_id, message_id, text, metadata=None):
        self.edited.append((chat_id, message_id, text, {"metadata": metadata} if metadata is not None else {}))
        return FakeResult(True, message_id)


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


def test_send_with_status_metadata_decorates_wait_state():
    adapter = FakeAdapter()
    runtime = FakeRuntime()
    wrap_adapter(adapter, runtime)

    result = asyncio.run(adapter.send("chat1", "⏳ Working — 3 min", metadata={"non_conversational": True}))

    sent_text = adapter.sent[0][1]
    assert "⏳ Working — 3 min" in sent_text
    assert "Neon" in sent_text
    assert "**Neon" in sent_text
    assert "$0.42" in sent_text
    assert SPONSOR_MARKER in sent_text
    assert "ADtention" not in sent_text
    assert result.success is True


async def _send_or_update_status_coro(adapter, chat_id, status_key, content):
    return await adapter.send(chat_id, content)


def test_send_from_gateway_status_helper_decorates_without_metadata():
    adapter = FakeAdapter(platform="discord")
    runtime = FakeRuntime()
    wrap_adapter(adapter, runtime)

    asyncio.run(_send_or_update_status_coro(adapter, "channel1", "lifecycle", "⏳ Working — 3 min"))

    assert "Neon" in adapter.sent[0][1]
    assert runtime.acked


async def _fake_gateway_status_helper_original(adapter, chat_id, status_key, content, metadata):
    return await adapter.send(chat_id, content, metadata=metadata)


def test_patch_gateway_status_helper_injects_render_scope_metadata(monkeypatch):
    gateway_run = importlib.import_module("gateway.run")
    monkeypatch.setattr(gateway_run, "_send_or_update_status_coro", _fake_gateway_status_helper_original)
    runtime = FakeRuntime()

    patch_gateway_status_helper(runtime)

    adapter = FakeAdapter(platform="telegram")
    original_metadata = {"existing": "value"}

    async def call_from_gateway_turn_frame():
        session_key = "telegram:chat1:topic1"
        run_generation = 7
        event_message_id = "msg-123"
        source = FakeSource(platform="telegram", chat_id="chat1", thread_id="topic1")
        assert session_key and run_generation and event_message_id and source
        return await gateway_run._send_or_update_status_coro(
            adapter,
            "chat1",
            "lifecycle",
            "⏳ Working — 3 min",
            original_metadata,
        )

    asyncio.run(call_from_gateway_turn_frame())

    metadata = adapter.sent[0][2]["metadata"]
    assert metadata is not original_metadata
    assert metadata["existing"] == "value"
    assert metadata["non_conversational"] is True
    assert metadata["adtention_render_scope"]
    assert "adtention_render_scope" not in original_metadata


def test_generic_send_does_not_decorate_prefix_spoofed_final_answer():
    adapter = FakeAdapter()
    runtime = FakeRuntime()
    wrap_adapter(adapter, runtime)

    asyncio.run(adapter.send("chat1", "⏳ Working — this is actually final content"))

    assert adapter.sent[0][1] == "⏳ Working — this is actually final content"
    assert runtime.acked == []


def test_send_does_not_decorate_unsupported_platform():
    adapter = FakeAdapter(platform="slack")
    runtime = FakeRuntime()
    wrap_adapter(adapter, runtime)

    asyncio.run(adapter.send("chat1", "⏳ Working — 3 min", metadata={"non_conversational": True}))

    assert "Neon" not in adapter.sent[0][1]
    assert runtime.acked == []


def test_ack_uses_platform_enum_value_not_repr():
    adapter = FakeAdapter(platform=EnumLikePlatform())
    runtime = FakeRuntime()
    wrap_adapter(adapter, runtime)

    asyncio.run(adapter.send("chat1", "⏳ Working — 3 min", metadata={"non_conversational": True}))

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

    asyncio.run(adapter.send("chat1", text="ignored by fake", content="⏳ Working — 3 min", metadata={"non_conversational": True}))

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

    asyncio.run(adapter.edit_message("chat1", "m1", text="ignored by fake", content="⏳ Working — 3 min", metadata={"non_conversational": True}))

    assert "Neon" in adapter.edited[0][3]["content"]
    assert adapter.edited[0][3]["finalize"] is True


def test_generic_edit_does_not_decorate_without_status_metadata():
    adapter = FakeAdapter()
    runtime = FakeRuntime()
    wrap_adapter(adapter, runtime)

    asyncio.run(adapter.edit_message("chat1", "m1", "⏳ Working — final answer edit"))

    assert adapter.edited[0][2] == "⏳ Working — final answer edit"
    assert runtime.acked == []


def test_telegram_wait_state_edit_requests_markdown_finalize():
    adapter = FakeAdapter(platform="telegram")
    runtime = FakeRuntime()
    wrap_adapter(adapter, runtime)

    asyncio.run(adapter.edit_message("chat1", "m1", "⏳ Working — 3 min", metadata={"non_conversational": True}))

    assert adapter.edited[0][3]["finalize"] is True


def test_legacy_telegram_edit_without_finalize_kw_does_not_break_delivery():
    adapter = LegacyTelegramAdapter()
    runtime = FakeRuntime()
    wrap_adapter(adapter, runtime)

    asyncio.run(adapter.edit_message("chat1", "m1", "⏳ Working — 3 min", metadata={"non_conversational": True}))

    assert "Neon" in adapter.edited[0][2]


def test_edit_replaces_existing_segment_not_duplicate():
    adapter = FakeAdapter()
    runtime = FakeRuntime()
    wrap_adapter(adapter, runtime)

    asyncio.run(adapter.edit_message("chat1", "m1", "⏳ Working — 3 min\n⊕ ADtention · Old", metadata={"non_conversational": True}))
    text = adapter.edited[0][2]

    assert text.count(SPONSOR_MARKER) == 1
    assert "Neon" in text
    assert "ADtention" not in text


def test_failed_send_does_not_ack_impression():
    adapter = FailingAdapter()
    runtime = FakeRuntime()
    wrap_adapter(adapter, runtime)

    asyncio.run(adapter.send("chat1", "⏳ Working — 3 min", metadata={"non_conversational": True}))

    assert runtime.acked == []


def test_successful_send_and_edit_ack_once_for_same_message():
    adapter = FakeAdapter()
    runtime = FakeRuntime()
    wrap_adapter(adapter, runtime)

    asyncio.run(adapter.send("chat1", "⏳ Working — 3 min", metadata={"non_conversational": True}))
    asyncio.run(adapter.edit_message("chat1", "m1", "⏳ Working — 4 min", metadata={"non_conversational": True}))

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
