from adtention_hermes.plugin import (
    on_post_llm_call,
    on_pre_gateway_dispatch,
    on_pre_llm_call,
    on_pre_tool_call,
    register,
)
from conftest import FakeGateway, FakeHookContext, FakeRuntime, fake_event


def test_registers_expected_hooks():
    ctx = FakeHookContext()
    register(ctx, runtime=FakeRuntime())
    assert "pre_gateway_dispatch" in ctx.hooks
    assert "pre_llm_call" in ctx.hooks
    assert "pre_tool_call" in ctx.hooks
    assert "post_tool_call" in ctx.hooks
    assert "post_llm_call" in ctx.hooks


def test_pre_gateway_dispatch_wraps_gateway_and_prefetches():
    gateway = FakeGateway()
    runtime = FakeRuntime()
    event = fake_event("Research foundation shade matching competitors", platform="telegram")

    result = on_pre_gateway_dispatch(event=event, gateway=gateway, runtime=runtime)

    assert result is None
    assert gateway.adapters["telegram"]._adtention_wrapped is True
    assert runtime.prefetch_calls
    assert runtime.prefetch_calls[0][2] == "business_research"


def test_adtention_command_is_handled_and_skips_llm():
    gateway = FakeGateway()
    runtime = FakeRuntime()
    event = fake_event("/adtention status", platform="telegram")

    result = on_pre_gateway_dispatch(event=event, gateway=gateway, runtime=runtime)

    assert result["action"] == "skip"
    assert gateway.adapters["telegram"].sent
    assert "enabled" in gateway.adapters["telegram"].sent[0][1].lower()


def test_pre_llm_call_returns_none_and_does_not_inject_context():
    runtime = FakeRuntime()
    result = on_pre_llm_call(
        session_id="s1",
        user_message="Research competitors",
        conversation_history=[{"role": "user", "content": "secret"}],
        platform="telegram",
        runtime=runtime,
    )
    assert result is None
    assert "secret" not in repr(runtime.classifications)


def test_pre_tool_call_records_tool_name_only():
    runtime = FakeRuntime()
    on_pre_tool_call(
        session_id="s1",
        tool_name="web_search",
        arguments={"query": "secret project"},
        runtime=runtime,
    )
    assert runtime.observed_tools["s1"] == ["web_search"]
    assert "secret project" not in repr(runtime.observed_tools)


def test_post_llm_call_is_noop_for_final_answers():
    runtime = FakeRuntime()
    result = on_post_llm_call(session_id="s1", response_text="Final answer", runtime=runtime)
    assert result is None
    assert "Final answer" not in repr(runtime.__dict__)
