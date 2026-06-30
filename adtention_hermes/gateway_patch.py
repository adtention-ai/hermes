"""Runtime gateway adapter wrapping for compatibility mode.

Hermes core does not currently expose a dedicated wait_state_segment hook. This
module provides the no-core-PR compatibility path by wrapping live Telegram /
Discord adapter methods and decorating only recognized wait-state/status text.
"""

from __future__ import annotations

import inspect
import sys
from collections.abc import Callable
from typing import Any

from .renderer import decorate_wait_state, is_wait_state
from .privacy import render_nonce

WRAPPED_FLAG = "_adtention_wrapped"
ORIGINALS_ATTR = "_adtention_originals"
SUPPORTED_METHODS = ("send", "edit_message", "send_or_update_status")
SUPPORTED_PLATFORMS = {"telegram", "discord"}


def wrap_gateway(gateway: Any, runtime: Any) -> None:
    patch_gateway_status_helper(runtime)
    adapters = getattr(gateway, "adapters", None) or getattr(gateway, "platform_adapters", None)
    if not adapters:
        return
    iterable = adapters.values() if isinstance(adapters, dict) else adapters
    for adapter in iterable:
        wrap_adapter(adapter, runtime)


def wrap_adapter(adapter: Any, runtime: Any) -> None:
    if getattr(adapter, WRAPPED_FLAG, False):
        return
    originals: dict[str, Callable] = {}
    for method_name in SUPPORTED_METHODS:
        original = getattr(adapter, method_name, None)
        if callable(original):
            originals[method_name] = original
            setattr(adapter, method_name, _make_wrapper(adapter, method_name, original, runtime))
    setattr(adapter, ORIGINALS_ATTR, originals)
    setattr(adapter, WRAPPED_FLAG, True)


def _make_wrapper(adapter: Any, method_name: str, original: Callable, runtime: Any) -> Callable:
    async def async_wrapper(*args, **kwargs):
        original_args = args
        original_kwargs = dict(kwargs)
        sponsor = None
        try:
            args, kwargs, sponsor = _decorate_call(adapter, method_name, original, args, dict(kwargs), runtime)
        except Exception:
            args, kwargs, sponsor = original_args, original_kwargs, None

        result = await _maybe_await(original(*args, **kwargs))
        if sponsor is not None and _send_succeeded(result):
            _ack_safely(adapter, method_name, args, kwargs, result, runtime, sponsor)
        return result

    def sync_wrapper(*args, **kwargs):
        original_args = args
        original_kwargs = dict(kwargs)
        sponsor = None
        try:
            args, kwargs, sponsor = _decorate_call(adapter, method_name, original, args, dict(kwargs), runtime)
        except Exception:
            args, kwargs, sponsor = original_args, original_kwargs, None

        result = original(*args, **kwargs)
        if inspect.isawaitable(result):
            return _await_and_ack(result, adapter, method_name, args, kwargs, runtime, sponsor)
        if sponsor is not None and _send_succeeded(result):
            _ack_safely(adapter, method_name, args, kwargs, result, runtime, sponsor)
        return result

    return async_wrapper if inspect.iscoroutinefunction(original) else sync_wrapper


async def _await_and_ack(awaitable, adapter, method_name, args, kwargs, runtime, sponsor):
    result = await awaitable
    if sponsor is not None and _send_succeeded(result):
        _ack_safely(adapter, method_name, args, kwargs, result, runtime, sponsor)
    return result


async def _maybe_await(value):
    if inspect.isawaitable(value):
        return await value
    return value


def _accepts_keyword(callable_obj: Callable, keyword: str) -> bool:
    try:
        signature = inspect.signature(callable_obj)
    except (TypeError, ValueError):
        return False
    return any(
        name == keyword or param.kind == inspect.Parameter.VAR_KEYWORD
        for name, param in signature.parameters.items()
    )


def _decorate_call(adapter: Any, method_name: str, original: Callable, args: tuple, kwargs: dict, runtime: Any):
    if hasattr(runtime, "is_enabled") and not runtime.is_enabled():
        return args, kwargs, None

    platform = _adapter_platform(adapter)
    if platform not in SUPPORTED_PLATFORMS:
        return args, kwargs, None

    render_scope = _render_scope_for_status_call(method_name, args, kwargs, platform)
    if not render_scope and not _is_explicit_status_call(method_name, kwargs):
        return args, kwargs, None

    locator = _find_text_locator(method_name, args, kwargs)
    if locator is None:
        return args, kwargs, None
    where, key, text = locator
    if not isinstance(text, str) or not is_wait_state(text):
        return args, kwargs, None

    sponsor = runtime.get_sponsor_for_render(platform=platform, render_scope=render_scope)
    if not sponsor:
        return args, kwargs, None
    sponsor = dict(sponsor)
    if render_scope:
        sponsor["_adtention_render_scope"] = render_scope

    new_text = decorate_wait_state(text, sponsor)
    if new_text == text:
        return args, kwargs, None

    can_finalize_telegram_edit = (
        method_name == "edit_message"
        and platform == "telegram"
        and _accepts_keyword(original, "finalize")
    )

    if where == "kw":
        kwargs[key] = new_text
        if can_finalize_telegram_edit:
            # TelegramAdapter only applies parse_mode/MarkdownV2 formatting on
            # finalize edits. Wait-state sponsor segments contain standard
            # Markdown for bold/link rendering, so decorated status edits must
            # request the formatted path instead of Telegram's raw streaming
            # edit path.
            kwargs["finalize"] = True
        return args, kwargs, sponsor

    mutable_args = list(args)
    mutable_args[key] = new_text
    if can_finalize_telegram_edit:
        kwargs["finalize"] = True
    return tuple(mutable_args), kwargs, sponsor


def patch_gateway_status_helper(runtime: Any) -> None:
    """Attach a stable render-scope token to Hermes status helper sends.

    Hermes' compatibility path falls back to ``adapter.send`` for adapters that
    do not implement ``send_or_update_status``. The helper itself is called from
    a per-turn status callback frame that still has the session/run identifiers;
    by wrapping the helper as a normal function (returning the original
    coroutine), we can inject a per-turn token into metadata before the coroutine
    is scheduled. This avoids process-global render-scope state for overlapping
    turns while leaving Hermes core untouched.
    """
    module = sys.modules.get("gateway.run")
    if module is None:
        # Avoid importing the full Hermes gateway just to discover whether the
        # helper exists. In real gateway execution gateway.run is already loaded;
        # in tests/CLI imports, pulling it in here can block unrelated sends.
        return
    original = getattr(module, "_send_or_update_status_coro", None)
    if not callable(original):
        return
    if getattr(original, "_adtention_status_helper_patched", False):
        setattr(original, "_adtention_runtime", runtime)
        return

    def patched(adapter, chat_id, status_key, content, metadata):
        scope_id = _scope_from_status_helper_caller(chat_id)
        if scope_id:
            metadata = _metadata_with_render_scope(metadata, scope_id)
        return original(adapter, chat_id, status_key, content, metadata)

    setattr(patched, "_adtention_status_helper_patched", True)
    setattr(patched, "_adtention_original", original)
    setattr(patched, "_adtention_runtime", runtime)
    setattr(module, "_send_or_update_status_coro", patched)


def _metadata_with_render_scope(metadata: Any, scope_id: str) -> dict[str, Any]:
    merged = dict(metadata) if isinstance(metadata, dict) else {}
    merged.setdefault("adtention_render_scope", scope_id)
    merged.setdefault("non_conversational", True)
    return merged


def _scope_from_status_helper_caller(chat_id: Any, *, max_depth: int = 12) -> str:
    frame = inspect.currentframe()
    try:
        frame = frame.f_back if frame is not None else None
        values: dict[str, Any] = {"chat_id": chat_id}
        depth = 0
        while frame is not None and depth < max_depth:
            local_vars = frame.f_locals
            for key in ("session_key", "run_generation", "event_message_id"):
                if values.get(key) is None and local_vars.get(key) is not None:
                    values[key] = local_vars.get(key)
            source = local_vars.get("source")
            if source is not None:
                values.setdefault("platform", getattr(source, "platform", None))
                values.setdefault("thread_id", getattr(source, "thread_id", None))
                values.setdefault("source_message_id", getattr(source, "message_id", None))
            frame = frame.f_back
            depth += 1
        if not any(values.get(key) is not None for key in ("session_key", "run_generation", "event_message_id", "source_message_id")):
            return ""
        return render_nonce(
            "gateway-turn",
            values.get("session_key"),
            values.get("run_generation"),
            values.get("event_message_id") or values.get("source_message_id"),
            values.get("platform"),
            values.get("chat_id"),
            values.get("thread_id"),
        )
    finally:
        del frame


def _render_scope_for_status_call(method_name: str, args: tuple, kwargs: dict, platform: str) -> str | None:
    metadata = kwargs.get("metadata")
    if isinstance(metadata, dict):
        scope = metadata.get("adtention_render_scope") or metadata.get("render_scope")
        if scope:
            return str(scope)
    return None


def _is_explicit_status_call(method_name: str, kwargs: dict) -> bool:
    """Only decorate actual gateway status paths, not arbitrary sends.

    ``send_or_update_status`` is Hermes' explicit status helper. Some adapters
    without that helper fall back to plain ``send``; those sends must either opt
    in via status metadata or come directly from Hermes' status helper so a user
    cannot spoof billing by making final content start with "⏳ Working".
    """
    if method_name == "send_or_update_status":
        return True
    metadata = kwargs.get("metadata")
    if isinstance(metadata, dict) and any(
        bool(metadata.get(key))
        for key in ("non_conversational", "status", "status_key", "hermes_status")
    ):
        return True
    return _called_from_gateway_status_helper()


def _called_from_gateway_status_helper(*, max_depth: int = 8) -> bool:
    frame = inspect.currentframe()
    try:
        frame = frame.f_back if frame is not None else None
        depth = 0
        while frame is not None and depth < max_depth:
            if frame.f_code.co_name == "_send_or_update_status_coro":
                return True
            frame = frame.f_back
            depth += 1
        return False
    finally:
        del frame


def _find_text_locator(method_name: str, args: tuple, kwargs: dict):
    # Hermes platform adapters name the user-visible message body ``content``;
    # some tests/older helpers use ``text``. Prefer content when both appear.
    for key_name in ("content", "text"):
        if key_name in kwargs and isinstance(kwargs[key_name], str):
            return ("kw", key_name, kwargs[key_name])

    preferred_index = {
        "send": 1,
        "edit_message": 2,
        "send_or_update_status": 2,  # (chat_id, status_key, content, ...)
    }.get(method_name)
    if preferred_index is not None and len(args) > preferred_index and isinstance(args[preferred_index], str):
        return ("arg", preferred_index, args[preferred_index])

    for index in range(len(args) - 1, -1, -1):
        if isinstance(args[index], str):
            return ("arg", index, args[index])
    return None


def _platform_name(value: Any) -> str:
    if value is None:
        return "unknown"
    raw = getattr(value, "value", value)
    text = str(raw or "unknown").strip().lower()
    if text.startswith("platform."):
        text = text.split(".", 1)[1]
    return text or "unknown"


def _adapter_platform(adapter: Any) -> str:
    for attr in ("platform", "name"):
        value = getattr(adapter, attr, None)
        if value:
            return _platform_name(value)
    class_name = adapter.__class__.__name__.lower()
    for platform in SUPPORTED_PLATFORMS:
        if platform in class_name:
            return platform
    return "unknown"


def _send_succeeded(result: Any) -> bool:
    if result is None:
        return True
    success = getattr(result, "success", None)
    if success is False:
        return False
    if isinstance(result, dict) and result.get("success") is False:
        return False
    return True


def _message_id(method_name: str, args: tuple, kwargs: dict, result: Any) -> str | None:
    result_id = getattr(result, "message_id", None) or getattr(result, "id", None)
    if result_id:
        return str(result_id)
    if isinstance(result, dict):
        result_id = result.get("message_id") or result.get("id")
        if result_id:
            return str(result_id)
    if "message_id" in kwargs:
        return str(kwargs["message_id"])
    if method_name == "edit_message" and len(args) > 1:
        return str(args[1])
    return None


def _ack_safely(adapter: Any, method_name: str, args: tuple, kwargs: dict, result: Any, runtime: Any, sponsor: dict) -> None:
    try:
        message_id = _message_id(method_name, args, kwargs, result)
        if not message_id:
            return
        platform = _adapter_platform(adapter)
        runtime.ack_rendered_once(sponsor, platform, message_id)
    except Exception:
        # Billing/telemetry must never break platform message delivery.
        return
