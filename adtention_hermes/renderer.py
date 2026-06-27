"""Pure wait-state sponsor rendering helpers.

This module is intentionally dependency-free and side-effect-free. It never
knows about Hermes internals, API clients, state, or billing. It only decides
whether text looks like a wait-state/status message and, if so, appends a
bounded one-line sponsor segment.
"""

from __future__ import annotations

import re
from typing import Mapping, Any

SPONSOR_LINK_LABEL = "More Info"
# Invisible Separator (U+2063). It lets edits identify our own hidden-brand
# sponsor line without showing ADtention branding or stripping arbitrary host
# lines that happen to contain a "More Info" link.
SPONSOR_MARKER = "\u2063"
LEGACY_SPONSOR_MARKERS = ("⊕ ADtention ·", "⊕ ADtention")
_MAX_SEGMENT_CHARS = 280
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_WHITESPACE = re.compile(r"\s+")

_WAIT_PREFIXES = (
    "⏳ working",
    "⌛ working",
    "working —",
    "working -",
    "still working",
    "processing —",
    "processing -",
)

# Tool/debug progress can fire many times per turn and is easier to spoof than
# lifecycle heartbeats. Until the API has an explicit non-billable render class,
# keep these messages unsponsored instead of crediting them like user-visible
# waiting heartbeats.
_NON_BILLABLE_PREFIXES = (
    "tool progress",
    "running tool",
    "executing tool",
)


def _is_existing_segment_line(line: str) -> bool:
    stripped = line.strip()
    if any(stripped.startswith(marker) for marker in LEGACY_SPONSOR_MARKERS):
        return True
    return stripped.startswith(SPONSOR_MARKER)


def strip_existing_segment(text: str) -> str:
    """Remove previously-rendered sponsor segment lines from ``text``."""
    if not isinstance(text, str):
        return text
    lines = [line for line in text.splitlines() if not _is_existing_segment_line(line)]
    return "\n".join(lines).rstrip()


def is_wait_state(text: str) -> bool:
    """Return True if ``text`` looks like a Hermes wait-state/status bubble."""
    if not isinstance(text, str) or not text.strip():
        return False
    clean = strip_existing_segment(text).strip()
    if not clean:
        return False
    first_line = clean.splitlines()[0].strip().lower()
    if any(first_line.startswith(prefix) for prefix in _NON_BILLABLE_PREFIXES):
        return False
    return any(first_line.startswith(prefix) for prefix in _WAIT_PREFIXES)


def _sanitize_one_line(value: Any, *, max_chars: int = _MAX_SEGMENT_CHARS) -> str:
    text = "" if value is None else str(value)
    text = _CONTROL_CHARS.sub("", text)
    text = _WHITESPACE.sub(" ", text).strip()
    if len(text) > max_chars:
        text = text[: max(0, max_chars - 1)].rstrip() + "…"
    return text


def _escape_markdown_text(value: str) -> str:
    """Escape Markdown control characters inside bold sponsor copy."""
    return re.sub(r"([\\`*_\[\]()])", r"\\\1", value)


def _sanitize_link_url(value: Any) -> str:
    url = _sanitize_one_line(value, max_chars=180)
    if not url.startswith(("https://", "http://")):
        return ""
    return url.replace("(", "%28").replace(")", "%29")


def _format_balance(sponsor: Mapping[str, Any]) -> str:
    if sponsor.get("balance_display"):
        return _escape_markdown_text(_sanitize_one_line(sponsor["balance_display"], max_chars=32))
    value = sponsor.get("balance_usd")
    if isinstance(value, (int, float)):
        return f"${value:.2f}"
    return ""


def _build_segment(sponsor: Mapping[str, Any], *, max_segment_chars: int = _MAX_SEGMENT_CHARS) -> str:
    sponsor_text = _sanitize_one_line(sponsor.get("text", ""), max_chars=max_segment_chars)
    balance = _format_balance(sponsor)
    click_url = _sanitize_link_url(sponsor.get("click_url", ""))

    if not sponsor_text or not click_url:
        return ""

    parts = []
    if balance:
        parts.append(balance)
    parts.append(f"**{_escape_markdown_text(sponsor_text)}**")
    line = " · ".join(parts)
    link = f"[{SPONSOR_LINK_LABEL}]({click_url})"
    return f"{SPONSOR_MARKER}{line} → {link}"


def append_sponsor_segment(text: str, sponsor: Mapping[str, Any], *, max_chars: int = 4000) -> str:
    """Append a sanitized sponsor segment, replacing any prior sponsor line."""
    base = strip_existing_segment(text)
    segment = _build_segment(sponsor)
    if not segment:
        return base
    combined = f"{base}\n{segment}" if base else segment
    if len(combined) <= max_chars:
        return combined

    # Preserve the wait-state text first; truncate only the sponsor line.
    separator_len = 1 if base else 0
    available_for_segment = max_chars - len(base) - separator_len
    if available_for_segment <= len(SPONSOR_LINK_LABEL) + 4:
        return base[:max_chars]

    truncated_segment = segment[: max(0, available_for_segment - 1)].rstrip() + "…"
    return f"{base}\n{truncated_segment}" if base else truncated_segment


def decorate_wait_state(text: str, sponsor: Mapping[str, Any] | None, *, max_chars: int = 4000) -> str:
    """Return decorated text only when ``text`` is a recognized wait state."""
    if not sponsor or not is_wait_state(text):
        return text
    return append_sponsor_segment(text, sponsor, max_chars=max_chars)
