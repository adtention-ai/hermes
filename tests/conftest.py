from dataclasses import dataclass


class FakeResult:
    def __init__(self, success=True, message_id="m1"):
        self.success = success
        self.message_id = message_id


class FakeAdapter:
    def __init__(self, platform: object = "telegram"):
        self.platform = platform
        self.sent = []
        self.edited = []
        self.status_updates = []

    async def send(self, chat_id, text, **kwargs):
        self.sent.append((chat_id, text, kwargs))
        return FakeResult(True, "m1")

    async def edit_message(self, chat_id, message_id, text, **kwargs):
        self.edited.append((chat_id, message_id, text, kwargs))
        return FakeResult(True, message_id)

    async def send_or_update_status(self, chat_id, status_key_or_text, content=None, **kwargs):
        text = content if content is not None else status_key_or_text
        self.status_updates.append((chat_id, text, kwargs))
        return FakeResult(True, kwargs.get("message_id", "status1"))


class FailingAdapter(FakeAdapter):
    async def send(self, chat_id, text, **kwargs):
        self.sent.append((chat_id, text, kwargs))
        return FakeResult(False, "m1")


class ExplodingAdapter(FakeAdapter):
    async def send(self, chat_id, text, **kwargs):
        raise RuntimeError("base send failed")


@dataclass
class FakeSource:
    platform: object = "telegram"
    chat_id: str = "chat1"
    thread_id: str | None = None
    chat_name: str = "Test Chat"
    chat_topic: str | None = None
    user_id: str = "user1"


@dataclass
class FakeEvent:
    text: str
    source: FakeSource
    message_type: str = "text"
    media_types: list[str] | None = None


def fake_event(text, platform: object = "telegram"):
    return FakeEvent(text=text, source=FakeSource(platform=platform))


class FakeGateway:
    def __init__(self, platforms=("telegram",)):
        self.adapters = {platform: FakeAdapter(platform) for platform in platforms}


class FakeHookContext:
    def __init__(self):
        self.hooks = {}

    def register_hook(self, name, fn):
        self.hooks[name] = fn


SPONSOR = {
    "text": "Neon: Postgres for AI agents",
    "creative_id": "cr_1",
    "impression_id": "imp_1",
    "click_url": "https://api.adtention.ai/v1/click/imp_1",
    "balance_usd": 0.42,
}


class FakeRuntime:
    def __init__(self, sponsor=None, enabled=True):
        self.sponsor = sponsor if sponsor is not None else dict(SPONSOR)
        self.enabled = enabled
        self.acked = []
        self.rendered = set()
        self.observed_tools = {}
        self.classifications = {}
        self.prefetch_calls = []
        self.sent_commands = []

    def is_enabled(self):
        return self.enabled

    def get_sponsor_for_render(self, platform=None, session_key=None, render_scope=None):
        return self.sponsor

    def ack_rendered_once(self, sponsor, platform, message_id):
        key = (sponsor["creative_id"], platform, str(message_id))
        if key in self.rendered:
            return False
        self.rendered.add(key)
        self.acked.append({
            "creative_id": sponsor["creative_id"],
            "impression_id": sponsor["impression_id"],
            "platform": platform,
            "message_id": str(message_id),
        })
        return True

    def classify_and_store(self, session_key, **kwargs):
        from adtention_hermes.classifier import classify_turn
        result = classify_turn(**kwargs)
        self.classifications[session_key] = result
        return result

    def record_tool(self, session_key, tool_name):
        self.observed_tools.setdefault(session_key, []).append(tool_name)

    def prefetch_sponsor_async(self, session_key, classification, platform):
        self.prefetch_calls.append((session_key, classification.category, classification.category_v2, platform))

    def command_status(self):
        return {"enabled": self.enabled, "balance_usd": 0.42, "category_v2": "web_research", "sponsor": self.sponsor}

    def set_enabled(self, value):
        self.enabled = bool(value)


class BrokenRuntime(FakeRuntime):
    def get_sponsor_for_render(self, platform=None, session_key=None, render_scope=None):
        raise RuntimeError("boom")
