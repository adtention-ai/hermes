"""Privacy-safe ADtention API client."""

from __future__ import annotations

import json
import urllib.request
from typing import Any, Callable, Mapping

PostJSON = Callable[[str, dict[str, Any], float], dict[str, Any]]


class Client:
    CLIENT_TAG = "hermes"
    SERVE_ALLOWED_KEYS = {
        "publisher_id",
        "client",
        "category",
        "category_v2",
        "host",
        "surface",
        "platform",
        "nonce",
        "ack_required",
        "client_version",
    }
    ACK_ALLOWED_KEYS = {
        "publisher_id",
        "impression_id",
        "creative_id",
        "host",
        "surface",
        "platform",
        "render_nonce",
        "client_version",
    }
    REGISTER_ALLOWED_KEYS = {
        "install_id",
        "client",
        "host",
        "client_version",
    }

    def __init__(
        self,
        *,
        api_url: str = "https://api.adtention.ai",
        post_json: PostJSON | None = None,
        timeout: float = 5.0,
        client_version: str = "0.1.3",
    ):
        self.api_url = api_url.rstrip("/")
        self.post_json = post_json or self._urllib_post_json
        self.timeout = timeout
        self.client_version = client_version

    def _urllib_post_json(self, url: str, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=data,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                # Cloudflare Bot Fight Mode blocks Python's default urllib User-Agent
                # with Error 1010. Use an explicit product UA so the public API accepts
                # normal plugin traffic without sending any extra user data.
                "User-Agent": f"ADtention-Hermes/{self.client_version}",
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - URL is user-configured API endpoint.
            body = response.read().decode("utf-8")
        return json.loads(body) if body else {}

    def _validate_payload(self, payload: Mapping[str, Any], allowed_keys: set[str]) -> None:
        unexpected = set(payload) - allowed_keys
        if unexpected:
            raise ValueError(f"ADtention payload contains forbidden keys: {sorted(unexpected)}")

    def serve(
        self,
        *,
        publisher_id: str,
        category: str,
        category_v2: str | None,
        platform: str,
        nonce: str,
    ) -> dict[str, Any]:
        payload = {
            "publisher_id": publisher_id,
            "client": self.CLIENT_TAG,
            "category": category,
            "category_v2": category_v2,
            "host": "hermes",
            "surface": "hermes_wait_state",
            "platform": platform,
            "nonce": nonce,
            "ack_required": True,
            "client_version": self.client_version,
        }
        payload = {key: value for key, value in payload.items() if value is not None}
        self._validate_payload(payload, self.SERVE_ALLOWED_KEYS)
        return self.post_json(f"{self.api_url}/v1/serve", payload, self.timeout)

    def ack_rendered(
        self,
        *,
        publisher_id: str,
        impression_id: str,
        creative_id: str,
        platform: str,
        render_nonce: str,
    ) -> dict[str, Any]:
        payload = {
            "publisher_id": publisher_id,
            "impression_id": impression_id,
            "creative_id": creative_id,
            "host": "hermes",
            "surface": "hermes_wait_state",
            "platform": platform,
            "render_nonce": render_nonce,
            "client_version": self.client_version,
        }
        self._validate_payload(payload, self.ACK_ALLOWED_KEYS)
        return self.post_json(f"{self.api_url}/v1/rendered", payload, self.timeout)

    def register_install(self, *, install_id: str) -> dict[str, Any]:
        payload = {
            "install_id": install_id,
            "client": self.CLIENT_TAG,
            "host": "hermes",
            "client_version": self.client_version,
        }
        self._validate_payload(payload, self.REGISTER_ALLOWED_KEYS)
        return self.post_json(f"{self.api_url}/v1/register", payload, self.timeout)
