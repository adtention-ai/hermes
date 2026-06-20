"""Pure wait-state sponsor rendering helpers.

This module is intentionally dependency-free and side-effect-free. It never
knows about Hermes internals, API clients, state, or billing. It only decides
whether text looks like a wait-state/status message and, if so, appends a
bounded one-line sponsor segment.
"""

from __future__ import annotations

import re
from typing import Mapping, Any

SPONSOR_MARKER = "⊕ ADtention ·"
_MAX_SEGMENT_CHARS = 280
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_WHITESPACE = re.compile(r"\s+")

_WAIT_PREFIXES = (
    "⏳ working",
    "⌛ working",
    "working —",
    "working -",
    "still working",
    "tool progress",
    "running tool",
    "executing tool",
    "processing —",
    "processing -",
)


def strip_existing_segment(text: str) -> str:
    """Remove previously-rendered ADtention segment lines from ``text``."""
    if not isinstance(text, str):
        return text
    lines = [line for line in text.splitlines() if not line.strip().startswith(SPONSOR_MARKER)]
    return "\n".join(lines).rstrip()


def is_wait_state(text: str) -> bool:
    """Return True if ``text`` looks like a Hermes wait-state/status bubble."""
    if not isinstance(text, str) or not text.strip():
        return False
    clean = strip_existing_segment(text).strip()
    if not clean:
        return False
    first_line = clean.splitlines()[0].strip().lower()
    return any(first_line.startswith(prefix) for prefix in _WAIT_PREFIXES)


def _sanitize_one_line(value: Any, *, max_chars: int = _MAX_SEGMENT_CHARS) -> str:
    text = "" if value is None else str(value)
    text = _CONTROL_CHARS.sub("", text)
    text = _WHITESPACE.sub(" ", text).strip()
    if len(text) > max_chars:
        text = text[: max(0, max_chars - 1)].rstrip() + "…"
    return text


def _format_balance(sponsor: Mapping[str, Any]) -> str:
    if sponsor.get("balance_display"):
        return _sanitize_one_line(sponsor["balance_display"], max_chars=32)
    value = sponsor.get("balance_usd")
    if isinstance(value, (int, float)):
        return f"${value:.2f}"
    return ""


def _build_segment(sponsor: Mapping[str, Any], *, max_segment_chars: int = _MAX_SEGMENT_CHARS) -> str:
    sponsor_text = _sanitize_one_line(sponsor.get("text", ""), max_chars=max_segment_chars)
    balance = _format_balance(sponsor)
    click_url = _sanitize_one_line(sponsor.get("click_url", ""), max_chars=180)

    parts = [SPONSOR_MARKER]
    if balance:
        parts.append(balance)
    if sponsor_text:
        parts.append(sponsor_text)
    line = " · ".join(parts)
    if click_url:
        line = f"{line} → {click_url}"
    return line


def append_sponsor_segment(text: str, sponsor: Mapping[str, Any], *, max_chars: int = 4000) -> str:
    """Append a sanitized sponsor segment, replacing any prior ADtention line."""
    base = strip_existing_segment(text)
    segment = _build_segment(sponsor)
    combined = f"{base}\n{segment}" if base else segment
    if len(combined) <= max_chars:
        return combined

    # Preserve the wait-state text first; truncate only the sponsor line.
    separator_len = 1 if base else 0
    available_for_segment = max_chars - len(base) - separator_len
    if available_for_segment <= len(SPONSOR_MARKER) + 4:
        return base[:max_chars]

    truncated_segment = segment[: max(0, available_for_segment - 1)].rstrip() + "…"
    return f"{base}\n{truncated_segment}" if base else truncated_segment


def decorate_wait_state(text: str, sponsor: Mapping[str, Any] | None, *, max_chars: int = 4000) -> str:
    """Return decorated text only when ``text`` is a recognized wait state."""
    if not sponsor or not is_wait_state(text):
        return text
    return append_sponsor_segment(text, sponsor, max_chars=max_chars)
