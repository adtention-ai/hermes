import pytest

from adtention_hermes.client import Client


def test_serve_payload_contains_only_allowed_keys():
    sent = []

    def fake_post(url, payload, timeout):
        sent.append((url, payload, timeout))
        return {
            "text": "Neon: Postgres for AI agents",
            "creative_id": "cr_1",
            "impression_id": "imp_1",
            "click_url": "https://api.adtention.ai/v1/click/imp_1",
            "balance_usd": 0.42,
        }

    client = Client(api_url="https://api.adtention.ai", post_json=fake_post)
    sponsor = client.serve(
        publisher_id="pub_1",
        category="data",
        category_v2="web_research",
        platform="telegram",
        nonce="n1",
    )

    payload = sent[0][1]
    assert sponsor["creative_id"] == "cr_1"
    assert set(payload) <= {
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


def test_serve_payload_tags_hermes_client():
    sent = []

    def fake_post(url, payload, timeout):
        sent.append(payload)
        return {
            "text": "Neon: Postgres for AI agents",
            "creative_id": "cr_1",
            "impression_id": "imp_1",
            "click_url": "https://api.adtention.ai/v1/click/imp_1",
        }

    client = Client(api_url="https://api.adtention.ai", post_json=fake_post)
    client.serve(
        publisher_id="pub_1",
        category="data",
        category_v2="web_research",
        platform="telegram",
        nonce="n1",
    )

    assert sent[0]["client"] == "hermes"


def test_register_payload_tags_hermes_client():
    sent = []

    def fake_post(url, payload, timeout):
        sent.append(payload)
        return {"publisher_id": "pub_1"}

    client = Client(api_url="https://api.adtention.ai", post_json=fake_post)
    client.register_install(install_id="install_1")

    assert sent[0]["client"] == "hermes"


def test_register_payload_sends_normalized_referrer_code_only():
    sent = []

    def fake_post(url, payload, timeout):
        sent.append(payload)
        return {"publisher_id": "pub_1"}

    client = Client(api_url="https://api.adtention.ai", post_json=fake_post)
    client.register_install(install_id="install_1", referrer="https://adtention.ai/r/H3R7VMJ?utm_secret=do-not-send")

    assert sent[0]["ref"] == "h3r7vmj"
    assert "referrer" not in sent[0]
    assert "referral_url" not in sent[0]
    assert "utm_secret" not in repr(sent[0])


def test_register_payload_omits_invalid_referrer_values():
    sent = []

    def fake_post(url, payload, timeout):
        sent.append(payload)
        return {"publisher_id": "pub_1"}

    client = Client(api_url="https://api.adtention.ai", post_json=fake_post)
    client.register_install(install_id="install_1", referrer="https://evil.tld/r/not-a-code")

    assert "ref" not in sent[0]


def test_serve_payload_rejects_prompt_like_extra_fields():
    client = Client(api_url="https://api.adtention.ai", post_json=lambda *_: {})
    with pytest.raises(ValueError):
        client._validate_payload({"publisher_id": "p", "prompt": "secret"}, Client.SERVE_ALLOWED_KEYS)


def test_ack_payload_contains_no_chat_id_or_message_text():
    sent = []

    def fake_post(url, payload, timeout):
        sent.append(payload)
        return {"ok": True}

    client = Client(api_url="https://api.adtention.ai", post_json=fake_post)
    client.ack_rendered(
        publisher_id="pub_1",
        impression_id="imp_1",
        creative_id="cr_1",
        platform="telegram",
        render_nonce="hashed-or-local-nonce",
    )

    payload = sent[0]
    assert "chat_id" not in payload
    assert "text" not in payload
    assert "message" not in payload
    assert set(payload) <= Client.ACK_ALLOWED_KEYS


def test_register_payload_does_not_accept_user_content():
    client = Client(api_url="https://api.adtention.ai", post_json=lambda *_: {})
    with pytest.raises(ValueError):
        client._validate_payload({"install_id": "i", "conversation_history": []}, Client.REGISTER_ALLOWED_KEYS)
