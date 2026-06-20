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
    assert "prompts" in text.lower()
    assert "never leave" in text.lower()


def test_unknown_command_returns_help():
    text = handle_command("/adtention wat", FakeRuntime())
    assert "/adtention status" in text
