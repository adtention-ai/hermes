"""Hermes plugin entrypoint and lifecycle hooks."""

from __future__ import annotations

import asyncio
import inspect
import os
import threading
import time
from pathlib import Path
from typing import Any

from .classifier import classify_turn
from .client import Client
from .commands import handle_command
from . import autoupdate as autoupdate_module
from .autoupdate import ensure_default_autoupdate
from .gateway_patch import _platform_name, wrap_gateway
from .privacy import render_nonce
from .referral import normalize_referrer, referral_url_for
from .state import StateStore

_RUNTIME = None
SPONSOR_CACHE_TTL_SECONDS = 120


def _hermes_home() -> Path:
    try:
        from hermes_constants import get_hermes_home  # type: ignore

        return Path(get_hermes_home())
    except Exception:
        return Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes"))


def _registration_referrer_from_env() -> str | None:
    for name in ("ADTENTION_REFERRER", "ADTENTION_REFERRAL_CODE", "ADTENTION_REFERRAL_URL"):
        normalized = normalize_referrer(os.environ.get(name))
        if normalized:
            return normalized
    return None


class Runtime:
    default_session_key = "default"

    def __init__(self, *, state: StateStore, client: Client, publisher_id: str | None = None):
        self.state = state
        self.client = client
        self.publisher_id = publisher_id or state.get_publisher_id() or os.environ.get("ADTENTION_PUBLISHER_ID")
        if self.publisher_id:
            self.state.set_publisher_id(self.publisher_id)
        self.install_id = state.get_or_create_install_id()

    @classmethod
    def from_env(cls) -> "Runtime":
        api_url = os.environ.get("ADTENTION_API_URL", "https://api.adtention.ai")
        base_dir = _hermes_home() / "adtention"
        return cls(state=StateStore(base_dir), client=Client(api_url=api_url))

    @classmethod
    def for_tests(cls, *, base_dir: str | Path, client: Any, publisher_id: str | None = None) -> "Runtime":
        return cls(state=StateStore(base_dir), client=client, publisher_id=publisher_id)

    def is_enabled(self) -> bool:
        return self.state.is_enabled()

    def set_enabled(self, enabled: bool) -> None:
        self.state.set_enabled(enabled)

    def autoupdate_status(self) -> dict[str, Any]:
        return autoupdate_module.autoupdate_status()

    def enable_autoupdate(self) -> dict[str, Any]:
        return autoupdate_module.enable_autoupdate()

    def disable_autoupdate(self) -> dict[str, Any]:
        return autoupdate_module.disable_autoupdate()

    def command_status(self) -> dict[str, Any]:
        classification = self.state.get_classification(self.default_session_key) or {}
        sponsor = self.state.get_sponsor(
            self.default_session_key,
            max_age_seconds=SPONSOR_CACHE_TTL_SECONDS,
        )
        return {
            "enabled": self.state.is_enabled(),
            "balance_usd": sponsor.get("balance_usd") if sponsor else None,
            "category_v2": classification.get("category_v2", "general"),
            "sponsor": sponsor,
            "referral": self.state.get_referral(),
        }

    def _remember_registration(self, registration: dict[str, Any]) -> str | None:
        publisher_id = registration.get("publisher_id")
        if publisher_id:
            self.publisher_id = str(publisher_id)
            self.state.set_publisher_id(self.publisher_id)
        referral_code = registration.get("referral_code")
        referral_url = registration.get("referral_url") or referral_url_for(referral_code)
        if referral_code or referral_url:
            self.state.set_referral(referral_code=referral_code, referral_url=referral_url)
        return self.publisher_id

    def _register_install(self) -> str | None:
        kwargs = {"install_id": self.install_id}
        referrer = _registration_referrer_from_env()
        if referrer:
            kwargs["referrer"] = referrer
        return self._remember_registration(self.client.register_install(**kwargs))

    def referral_status(self) -> dict[str, str]:
        referral = self.state.get_referral()
        if referral:
            return referral
        try:
            if not self.publisher_id:
                self._register_install()
            elif hasattr(self.client, "balance"):
                balance = self.client.balance(publisher_id=self.publisher_id)
                if isinstance(balance, dict):
                    self.state.set_referral(
                        referral_code=balance.get("referral_code"),
                        referral_url=balance.get("referral_url") or referral_url_for(balance.get("referral_code")),
                    )
        except Exception:
            return self.state.get_referral()
        return self.state.get_referral()

    def classify_and_store(self, session_key: str, **kwargs) -> Any:
        observed_tools = kwargs.pop("observed_tools", None) or self.state.get_observed_tools(session_key)
        classification = classify_turn(observed_tools=observed_tools, **kwargs)
        self.state.save_classification(session_key, classification)
        return classification

    def record_tool(self, session_key: str, tool_name: str) -> None:
        self.state.record_tool(session_key, tool_name)

    def get_sponsor_for_render(
        self,
        platform: str | None = None,
        session_key: str | None = None,
        render_scope: str | None = None,
    ) -> dict[str, Any] | None:
        if not self.is_enabled():
            return None
        scope_id = render_scope or self.state.get_setting("current_render_scope_id")
        if not self.state.can_render_in_scope(scope_id):
            return None
        session = session_key or self.default_session_key
        sponsor = self.state.get_sponsor(
            session,
            max_age_seconds=SPONSOR_CACHE_TTL_SECONDS,
        )
        impression_id = sponsor.get("impression_id") if sponsor else None
        if impression_id and self.state.has_rendered_impression(impression_id):
            self.state.consume_sponsor(session, impression_id)
            return None
        return sponsor

    def begin_render_scope(self, session_key: str, platform: str) -> None:
        scope_id = render_nonce(self.install_id, session_key, platform, time.time_ns())
        self.state.begin_render_scope(scope_id)

    def prefetch_sponsor_async(self, session_key: str, classification: Any, platform: str) -> None:
        if not self.is_enabled():
            return
        if not self.state.can_refresh_sponsor(min_seconds=15):
            return
        self.state.mark_refreshed()

        def worker():
            # Let the current Hermes wait-state render continue without racing on an
            # immediate first send in tests or in real gateway handlers.
            time.sleep(0.05)
            try:
                publisher_id = self.publisher_id
                if not publisher_id:
                    publisher_id = self._register_install()
                    if not publisher_id:
                        return

                sponsor = self.client.serve(
                    publisher_id=publisher_id,
                    category=classification.category,
                    category_v2=classification.category_v2,
                    platform=platform,
                    nonce=render_nonce(self.install_id, session_key, classification.category_v2, int(time.time() // 60)),
                )
                if sponsor:
                    # Compatibility with the current server contract while it still returns
                    # ad_id instead of creative_id and relative click paths.
                    if sponsor.get("ad_id") and not sponsor.get("creative_id"):
                        sponsor["creative_id"] = sponsor["ad_id"]
                    if str(sponsor.get("click_url", "")).startswith("/"):
                        sponsor["click_url"] = self.client.api_url + sponsor["click_url"]
                    self.state.save_sponsor(session_key, sponsor)
            except Exception:
                return

        threading.Thread(target=worker, name="adtention-sponsor-prefetch", daemon=True).start()

    def ack_rendered_once(self, sponsor: dict[str, Any], platform: str, message_id: str) -> bool:
        if not self.publisher_id:
            return False
        creative_id = sponsor.get("creative_id")
        impression_id = sponsor.get("impression_id")
        render_scope = sponsor.get("_adtention_render_scope")
        if not creative_id or not impression_id:
            return False
        if not self.state.mark_rendered_once((impression_id, creative_id, platform, message_id)):
            self.state.mark_scope_rendered(render_scope)
            self.state.consume_sponsor(self.default_session_key, impression_id)
            return False
        nonce = render_nonce(creative_id, platform, message_id)
        try:
            self.client.ack_rendered(
                publisher_id=self.publisher_id,
                impression_id=impression_id,
                creative_id=creative_id,
                platform=platform,
                render_nonce=nonce,
            )
        finally:
            self.state.mark_scope_rendered(render_scope)
            self.state.consume_sponsor(self.default_session_key, impression_id)
        return True


def _runtime(explicit: Runtime | None = None) -> Runtime:
    global _RUNTIME
    if explicit is not None:
        return explicit
    if _RUNTIME is None:
        _RUNTIME = Runtime.from_env()
    return _RUNTIME


def register(ctx, runtime: Any | None = None):
    rt = _runtime(runtime)
    if runtime is None:
        try:
            ensure_default_autoupdate()
        except Exception:
            # Auto-update setup must never prevent Hermes or ADtention from loading.
            pass
    hooks = {
        "pre_gateway_dispatch": lambda **kwargs: on_pre_gateway_dispatch(runtime=rt, **kwargs),
        "pre_llm_call": lambda **kwargs: on_pre_llm_call(runtime=rt, **kwargs),
        "pre_tool_call": lambda **kwargs: on_pre_tool_call(runtime=rt, **kwargs),
        "post_tool_call": lambda **kwargs: on_post_tool_call(runtime=rt, **kwargs),
        "post_llm_call": lambda **kwargs: on_post_llm_call(runtime=rt, **kwargs),
    }
    for name, fn in hooks.items():
        try:
            ctx.register_hook(name, fn)
        except Exception:
            # Older Hermes versions may not support every hook. Compatibility mode
            # only strictly needs pre_gateway_dispatch.
            continue
    try:
        ctx.register_command(
            "adtention",
            lambda raw_args="": handle_command(("/adtention " + str(raw_args or "")).strip(), rt),
            description="Manage ADtention wait-state sponsor segments",
            args_hint="[status|referral|on|off|privacy|sponsor|autoupdate]",
        )
    except Exception:
        # Older Hermes versions may not expose plugin slash-command registration.
        # The pre_gateway_dispatch fallback still handles literal /adtention text.
        pass
    return rt


def _event_text(event: Any) -> str:
    return str(getattr(event, "text", "") or "")


def _event_platform(event: Any) -> str:
    source = getattr(event, "source", None)
    return _platform_name(getattr(source, "platform", "unknown") or "unknown")


def _session_key(_event: Any | None = None, explicit: str | None = None) -> str:
    return explicit or Runtime.default_session_key


def _send_command_response(gateway: Any, event: Any, text: str) -> None:
    platform = _event_platform(event)
    source = getattr(event, "source", None)
    chat_id = getattr(source, "chat_id", None)
    adapter = None
    adapters = getattr(gateway, "adapters", None) or {}
    if isinstance(adapters, dict):
        adapter = adapters.get(platform)
    if adapter is None and adapters:
        adapter = next(iter(adapters.values()))
    if adapter is None or not hasattr(adapter, "send"):
        return

    result = adapter.send(chat_id, text)
    if inspect.isawaitable(result):
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            asyncio.run(result)
        else:
            loop.create_task(result)


def on_pre_gateway_dispatch(*, event: Any = None, gateway: Any = None, runtime: Any = None, **_kwargs):
    rt = _runtime(runtime)
    if gateway is not None:
        wrap_gateway(gateway, rt)

    text = _event_text(event)
    platform = _event_platform(event)
    if text.strip().lower().startswith("/adtention"):
        response = handle_command(text, rt)
        if gateway is not None:
            _send_command_response(gateway, event, response)
        return {"action": "skip", "reason": "adtention_command"}

    source = getattr(event, "source", None)
    session_key = _session_key(event)
    if hasattr(rt, "begin_render_scope"):
        rt.begin_render_scope(session_key, platform)
    classification = rt.classify_and_store(
        session_key,
        user_message=text,
        platform=platform,
        chat_name=getattr(source, "chat_name", "") if source else "",
        chat_topic=getattr(source, "chat_topic", "") if source else "",
        media_types=getattr(event, "media_types", None),
    )
    rt.prefetch_sponsor_async(session_key, classification, platform)
    return None


def on_pre_llm_call(*, session_id: str | None = None, user_message: str = "", platform: str = "", runtime: Any = None, **_kwargs):
    rt = _runtime(runtime)
    rt.classify_and_store(_session_key(explicit=session_id), user_message=user_message or "", platform=platform or "")
    return None


def on_pre_tool_call(*, session_id: str | None = None, tool_name: str = "", runtime: Any = None, **_kwargs):
    rt = _runtime(runtime)
    if tool_name:
        rt.record_tool(_session_key(explicit=session_id), tool_name)
    return None


def on_post_tool_call(*, session_id: str | None = None, tool_name: str = "", runtime: Any = None, **_kwargs):
    # Record the name again only if pre_tool_call was unavailable on an older host.
    rt = _runtime(runtime)
    if tool_name:
        rt.record_tool(_session_key(explicit=session_id), tool_name)
    return None


def on_post_llm_call(*, runtime: Any = None, **_kwargs):
    # Final assistant answers are intentionally untouched and not stored.
    _runtime(runtime)
    return None
