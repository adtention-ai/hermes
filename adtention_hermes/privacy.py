"""Privacy helpers for local-only identifiers."""

from __future__ import annotations

import hashlib


def stable_hash(value: str, *, prefix: str = "h") -> str:
    digest = hashlib.sha256(value.encode("utf-8", errors="ignore")).hexdigest()[:24]
    return f"{prefix}_{digest}"


def render_nonce(*parts: object) -> str:
    joined = "\x1f".join("" if part is None else str(part) for part in parts)
    return stable_hash(joined, prefix="render")
