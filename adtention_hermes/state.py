"""Local SQLite state for ADtention Hermes."""

from __future__ import annotations

import json
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any, Iterable

from .referral import normalize_referrer, referral_url_for


class StateStore:
    def __init__(self, base_dir: str | Path):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.base_dir / "adtention.sqlite3"
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        schema = """
                create table if not exists settings (
                    key text primary key,
                    value text not null
                );
                create table if not exists sponsor_cache (
                    session_key text primary key,
                    payload text not null,
                    updated_at integer not null
                );
                create table if not exists rendered (
                    render_key text primary key,
                    created_at integer not null
                );
                create table if not exists render_scopes (
                    scope_id text primary key,
                    rendered integer not null default 0,
                    updated_at integer not null
                );
                create table if not exists tools (
                    id integer primary key autoincrement,
                    session_key text not null,
                    tool_name text not null,
                    created_at integer not null
                );
                create table if not exists classifications (
                    session_key text primary key,
                    category text not null,
                    category_v2 text not null,
                    source text not null,
                    confidence real not null,
                    updated_at integer not null
                );
                """
        try:
            with self._connect() as conn:
                conn.executescript(schema)
        except sqlite3.DatabaseError as exc:
            message = str(exc).lower()
            if "not a database" not in message and "malformed" not in message:
                raise
            self._quarantine_corrupt_db()
            with self._connect() as conn:
                conn.executescript(schema)

    def _quarantine_corrupt_db(self) -> None:
        if not self.path.exists():
            return
        backup = self.path.with_name(f"{self.path.name}.corrupt-{time.strftime('%Y%m%d-%H%M%S')}-{time.time_ns()}.bak")
        self.path.replace(backup)

    def get_setting(self, key: str, default: str | None = None) -> str | None:
        with self._connect() as conn:
            row = conn.execute("select value from settings where key = ?", (key,)).fetchone()
        return row["value"] if row else default

    def set_setting(self, key: str, value: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "insert into settings(key, value) values(?, ?) on conflict(key) do update set value = excluded.value",
                (key, value),
            )

    def get_or_create_install_id(self) -> str:
        existing = self.get_setting("install_id")
        if existing:
            return existing
        install_id = f"hermes_{uuid.uuid4().hex}"
        self.set_setting("install_id", install_id)
        return install_id

    def get_publisher_id(self) -> str | None:
        return self.get_setting("publisher_id")

    def set_publisher_id(self, publisher_id: str) -> None:
        self.set_setting("publisher_id", publisher_id)

    def get_referral_code(self) -> str | None:
        return self.get_setting("referral_code")

    def get_referral_url(self) -> str | None:
        stored = self.get_setting("referral_url")
        if stored:
            return stored
        return referral_url_for(self.get_referral_code())

    def set_referral(self, *, referral_code: object | None = None, referral_url: object | None = None) -> None:
        code = normalize_referrer(referral_code) or normalize_referrer(referral_url)
        url = str(referral_url).strip() if referral_url else referral_url_for(code)
        if code:
            self.set_setting("referral_code", code)
        if url:
            self.set_setting("referral_url", url)

    def get_referral(self) -> dict[str, str]:
        referral_code = self.get_referral_code()
        referral_url = self.get_referral_url()
        out: dict[str, str] = {}
        if referral_code:
            out["referral_code"] = referral_code
        if referral_url:
            out["referral_url"] = referral_url
        return out

    def save_sponsor(self, session_key: str, sponsor: dict[str, Any], *, now: int | None = None) -> None:
        updated_at = int(time.time()) if now is None else int(now)
        with self._connect() as conn:
            conn.execute(
                """
                insert into sponsor_cache(session_key, payload, updated_at)
                values(?, ?, ?)
                on conflict(session_key) do update set payload = excluded.payload, updated_at = excluded.updated_at
                """,
                (session_key, json.dumps(sponsor, sort_keys=True), updated_at),
            )

    def get_sponsor(self, session_key: str, *, max_age_seconds: int | None = None, now: int | None = None) -> dict[str, Any] | None:
        current_time = int(time.time()) if now is None else int(now)
        with self._connect() as conn:
            row = conn.execute(
                "select payload, updated_at from sponsor_cache where session_key = ?",
                (session_key,),
            ).fetchone()
            if not row:
                return None
            if max_age_seconds is not None and current_time - int(row["updated_at"]) > int(max_age_seconds):
                conn.execute("delete from sponsor_cache where session_key = ?", (session_key,))
                return None
        return json.loads(row["payload"])

    def consume_sponsor(self, session_key: str, impression_id: str) -> None:
        """Remove the cached sponsor only if it is still the rendered impression."""
        if not impression_id:
            return
        with self._connect() as conn:
            row = conn.execute("select payload from sponsor_cache where session_key = ?", (session_key,)).fetchone()
            if not row:
                return
            try:
                payload = json.loads(row["payload"])
            except (TypeError, json.JSONDecodeError):
                payload = {}
            if str(payload.get("impression_id") or "") == str(impression_id):
                conn.execute("delete from sponsor_cache where session_key = ?", (session_key,))

    def is_enabled(self) -> bool:
        return self.get_setting("enabled", "1") != "0"

    def set_enabled(self, enabled: bool) -> None:
        self.set_setting("enabled", "1" if enabled else "0")

    def _render_key(self, key: Iterable[object]) -> str:
        from .privacy import render_nonce

        return render_nonce(*key)

    def mark_rendered_once(self, key: tuple[object, ...]) -> bool:
        # New callers pass (impression_id, creative_id, platform, message_id).
        # Dedupe on impression_id so a malicious client cannot credit the same
        # served impression repeatedly by changing local/platform message IDs.
        # Older callers that only pass (creative_id, platform, message_id) keep
        # their previous local-message dedupe semantics.
        render_key = self._render_key(("impression", key[0])) if len(key) >= 4 and key[0] else self._render_key(key)
        try:
            with self._connect() as conn:
                conn.execute(
                    "insert into rendered(render_key, created_at) values(?, ?)",
                    (render_key, int(time.time())),
                )
            return True
        except sqlite3.IntegrityError:
            return False

    def has_rendered_impression(self, impression_id: object) -> bool:
        if not impression_id:
            return False
        render_key = self._render_key(("impression", impression_id))
        with self._connect() as conn:
            row = conn.execute(
                "select 1 from rendered where render_key = ?",
                (render_key,),
            ).fetchone()
        return row is not None

    def begin_render_scope(self, scope_id: str) -> None:
        scope_id = str(scope_id or "").strip()
        if not scope_id:
            return
        with self._connect() as conn:
            conn.execute(
                """
                insert into render_scopes(scope_id, rendered, updated_at)
                values(?, 0, ?)
                on conflict(scope_id) do update set updated_at = excluded.updated_at
                """,
                (scope_id, int(time.time())),
            )
        self.set_setting("current_render_scope_id", scope_id)

    def can_render_in_scope(self, scope_id: str | None) -> bool:
        scope_id = str(scope_id or "").strip()
        if not scope_id:
            return self.can_render_in_current_scope()
        with self._connect() as conn:
            row = conn.execute(
                "select rendered from render_scopes where scope_id = ?",
                (scope_id,),
            ).fetchone()
        return not row or int(row["rendered"]) != 1

    def mark_scope_rendered(self, scope_id: str | None) -> None:
        scope_id = str(scope_id or "").strip()
        if not scope_id:
            self.mark_current_scope_rendered()
            return
        with self._connect() as conn:
            conn.execute(
                """
                insert into render_scopes(scope_id, rendered, updated_at)
                values(?, 1, ?)
                on conflict(scope_id) do update set rendered = 1, updated_at = excluded.updated_at
                """,
                (scope_id, int(time.time())),
            )

    def can_render_in_current_scope(self) -> bool:
        scope_id = self.get_setting("current_render_scope_id")
        if not scope_id:
            return True
        with self._connect() as conn:
            row = conn.execute(
                "select rendered from render_scopes where scope_id = ?",
                (scope_id,),
            ).fetchone()
        return not row or int(row["rendered"]) != 1

    def mark_current_scope_rendered(self) -> None:
        scope_id = self.get_setting("current_render_scope_id")
        if scope_id:
            self.mark_scope_rendered(scope_id)

    def can_refresh_sponsor(self, *, now: int | None = None, min_seconds: int = 15) -> bool:
        now = int(time.time()) if now is None else int(now)
        last = self.get_setting("last_refresh_at")
        if not last:
            return True
        return now - int(last) >= min_seconds

    def mark_refreshed(self, *, now: int | None = None) -> None:
        self.set_setting("last_refresh_at", str(int(time.time()) if now is None else int(now)))

    def record_tool(self, session_key: str, tool_name: str) -> None:
        # Store tool names only; never arguments/results.
        with self._connect() as conn:
            conn.execute(
                "insert into tools(session_key, tool_name, created_at) values(?, ?, ?)",
                (session_key, str(tool_name), int(time.time())),
            )

    def get_observed_tools(self, session_key: str) -> list[str]:
        with self._connect() as conn:
            rows = conn.execute(
                "select tool_name from tools where session_key = ? order by id asc",
                (session_key,),
            ).fetchall()
        return [row["tool_name"] for row in rows]

    def save_classification(self, session_key: str, classification: Any) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                insert into classifications(session_key, category, category_v2, source, confidence, updated_at)
                values(?, ?, ?, ?, ?, ?)
                on conflict(session_key) do update set
                    category = excluded.category,
                    category_v2 = excluded.category_v2,
                    source = excluded.source,
                    confidence = excluded.confidence,
                    updated_at = excluded.updated_at
                """,
                (
                    session_key,
                    classification.category,
                    classification.category_v2,
                    classification.source,
                    float(classification.confidence),
                    int(time.time()),
                ),
            )

    def get_classification(self, session_key: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "select category, category_v2, source, confidence from classifications where session_key = ?",
                (session_key,),
            ).fetchone()
        return dict(row) if row else None

    def dump_debug(self) -> dict[str, Any]:
        with self._connect() as conn:
            settings = {row["key"]: row["value"] for row in conn.execute("select key, value from settings")}
            tool_names = [row["tool_name"] for row in conn.execute("select tool_name from tools order by id")]
        return {"settings": settings, "tool_names": tool_names}
