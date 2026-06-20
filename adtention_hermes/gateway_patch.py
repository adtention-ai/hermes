"""Runtime gateway adapter wrapping for compatibility mode.

Hermes core does not currently expose a dedicated wait_state_segment hook. This
module provides the no-core-PR compatibility path by wrapping live Telegram /
Discord adapter methods and decorating only recognized wait-state/status text.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any

from .renderer import decorate_wait_state, is_wait_state

WRAPPED_FLAG = "_adtention_wrapped"
ORIGINALS_ATTR = "_adtention_originals"
SUPPORTED_METHODS = ("send", "edit_message", "send_or_update_status")
SUPPORTED_PLATFORMS = {"telegram", "discord"}


def wrap_gateway(gateway: Any, runtime: Any) -> None:
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
            args, kwargs, sponsor = _decorate_call(adapter, method_name, args, dict(kwargs), runtime)
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
            args, kwargs, sponsor = _decorate_call(adapter, method_name, args, dict(kwargs), runtime)
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


def _decorate_call(adapter: Any, method_name: str, args: tuple, kwargs: dict, runtime: Any):
    if hasattr(runtime, "is_enabled") and not runtime.is_enabled():
        return args, kwargs, None

    platform = _adapter_platform(adapter)
    if platform not in SUPPORTED_PLATFORMS:
        return args, kwargs, None

    locator = _find_text_locator(method_name, args, kwargs)
    if locator is None:
        return args, kwargs, None
    where, key, text = locator
    if not isinstance(text, str) or not is_wait_state(text):
        return args, kwargs, None

    sponsor = runtime.get_sponsor_for_render(platform=platform)
    if not sponsor:
        return args, kwargs, None

    new_text = decorate_wait_state(text, sponsor)
    if new_text == text:
        return args, kwargs, None

    if where == "kw":
        kwargs[key] = new_text
        return args, kwargs, sponsor

    mutable_args = list(args)
    mutable_args[key] = new_text
    return tuple(mutable_args), kwargs, sponsor


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
