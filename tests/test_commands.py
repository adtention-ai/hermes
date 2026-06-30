from adtention_hermes.commands import handle_command
from conftest import FakeRuntime


def test_status_command_reports_enabled_balance_and_category():
    text = handle_command("/adtention status", FakeRuntime())
    assert "enabled" in text.lower()
    assert "$0.42" in text
    assert "web_research" in text


def test_off_command_disables_plugin():
    runtime = FakeRuntime(enabled=True)
    text = handle_command("/adtention off", runtime)
    assert runtime.enabled is False
    assert "disabled" in text.lower()


def test_on_command_enables_plugin():
    runtime = FakeRuntime(enabled=False)
    text = handle_command("/adtention on", runtime)
    assert runtime.enabled is True
    assert "enabled" in text.lower()


def test_privacy_command_says_prompts_never_leave_machine():
    text = handle_command("/adtention privacy", FakeRuntime())
    lower = text.lower()
    assert "prompts" in lower
    assert "terminal output" in lower
    assert "tool output" in lower
    assert "client/version" in lower
    assert "impression/creative" in lower
    assert "never leave" in lower


def test_unknown_command_returns_help():
    text = handle_command("/adtention wat", FakeRuntime())
    assert "/adtention status" in text


def test_referral_command_reports_referral_link():
    text = handle_command("/adtention referral", FakeRuntime())

    assert "https://adtention.ai/r/h3r7vmj" in text
    assert "h3r7vmj" in text
    assert "15%" in text
    assert "hermes plugins install adtention-ai/hermes --enable --referral h3r7vmj" in text


def test_referral_command_reports_unavailable_state():
    runtime = FakeRuntime()
    runtime.referral = {}

    text = handle_command("/adtention referral", runtime)

    assert "not available yet" in text.lower()


class AutoUpdateRuntime(FakeRuntime):
    def __init__(self):
        super().__init__()
        self.autoupdate_disabled = False
        self.autoupdate_enabled = False

    def autoupdate_status(self):
        return {"enabled": True, "installed": True, "method": "systemd"}

    def disable_autoupdate(self):
        self.autoupdate_disabled = True
        return {"enabled": False, "installed": False, "method": "disabled"}

    def enable_autoupdate(self):
        self.autoupdate_enabled = True
        return {"enabled": True, "installed": True, "method": "systemd"}


def test_autoupdate_status_command_reports_default_on():
    text = handle_command("/adtention autoupdate status", AutoUpdateRuntime())
    assert "auto-update is enabled" in text.lower()
    assert "systemd" in text.lower()


def test_autoupdate_off_command_disables_daily_updates():
    runtime = AutoUpdateRuntime()
    text = handle_command("/adtention autoupdate off", runtime)
    assert runtime.autoupdate_disabled is True
    assert "disabled" in text.lower()


def test_autoupdate_on_command_enables_daily_updates():
    runtime = AutoUpdateRuntime()
    text = handle_command("/adtention autoupdate on", runtime)
    assert runtime.autoupdate_enabled is True
    assert "enabled" in text.lower()
