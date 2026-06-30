"""Referral-code helpers for ADtention Hermes.

Keep referral parsing privacy-preserving: callers may pass copied links or
campaign URLs, but the plugin sends only the normalized referral code to the
ADtention API.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

REFERRAL_URL_BASE = "https://adtention.ai/r/"
REFERRAL_CODE_RE = re.compile(r"^[abcdefghjkmnpqrstuvwxyz23456789]{7}$")


def referral_url_for(code: str | None) -> str | None:
    normalized = normalize_referrer(code)
    return f"{REFERRAL_URL_BASE}{normalized}" if normalized else None


def normalize_referrer(value: object | None) -> str | None:
    """Return a safe 7-char referral code, or None.

    Accept raw codes, uppercase codes, copied share URLs, and install URLs with
    a ref/referral_code/referrer query parameter. Reject invalid values and
    never return arbitrary URL/query text.
    """

    if value is None:
        return None
    raw = str(value).strip()
    if not raw or len(raw) > 2048:
        return None

    candidate = raw
    parsed = _parse_possible_url(raw)
    if parsed is not None:
        params = _query_params(parsed.query)
        candidate = (
            params.get("ref")
            or params.get("referral_code")
            or params.get("referrer")
            or _last_path_segment(parsed.path)
            or ""
        )

    candidate = str(candidate).strip().lstrip("#").lower()
    return candidate if REFERRAL_CODE_RE.fullmatch(candidate) else None


def _parse_possible_url(raw: str):
    parsed = urlparse(raw)
    if parsed.scheme and parsed.netloc:
        return parsed
    if "/" in raw:
        parsed = urlparse(f"https://{raw}")
        if parsed.netloc:
            return parsed
    return None


def _query_params(query: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for part in query.split("&"):
        if not part:
            continue
        key, _, value = part.partition("=")
        if key and value and key not in out:
            out[key] = value
    return out


def _last_path_segment(path: str) -> str | None:
    parts = [part for part in str(path or "").split("/") if part]
    return parts[-1] if parts else None
