from __future__ import annotations

import subprocess
from pathlib import Path

from adtention_hermes import autoupdate


def _git_plugin(tmp_path: Path) -> Path:
    plugin_dir = tmp_path / "plugins" / "adtention"
    (plugin_dir / ".git").mkdir(parents=True)
    return plugin_dir


def test_default_on_installs_daily_systemd_timer_for_git_checkout(tmp_path):
    plugin_dir = _git_plugin(tmp_path)
    hermes_home = tmp_path / "home"
    systemd_dir = tmp_path / "systemd-user"
    calls: list[list[str]] = []

    def runner(cmd, **_kwargs):
        calls.append(list(cmd))
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    result = autoupdate.ensure_default_autoupdate(
        plugin_dir=plugin_dir,
        hermes_home=hermes_home,
        systemd_user_dir=systemd_dir,
        runner=runner,
        which=lambda name: f"/usr/bin/{name}" if name in {"systemctl", "hermes"} else None,
    )

    assert result["enabled"] is True
    assert result["installed"] is True
    assert result["method"] == "systemd"
    script = hermes_home / "adtention" / "adtention-autoupdate.sh"
    assert script.exists()
    assert "hermes plugins update adtention" in script.read_text()
    assert "hermes gateway restart" in script.read_text()
    assert "git diff --quiet" in script.read_text()
    assert (systemd_dir / "adtention-autoupdate.service").exists()
    timer = (systemd_dir / "adtention-autoupdate.timer").read_text()
    assert "OnCalendar=*-*-* 04:" in timer
    assert "RandomizedDelaySec=2h" in timer
    assert ["/usr/bin/systemctl", "--user", "daemon-reload"] in calls
    assert ["/usr/bin/systemctl", "--user", "enable", "--now", "adtention-autoupdate.timer"] in calls


def test_disabled_sentinel_prevents_default_auto_install(tmp_path):
    plugin_dir = _git_plugin(tmp_path)
    hermes_home = tmp_path / "home"
    calls = []
    autoupdate.disable_autoupdate(
        hermes_home=hermes_home,
        systemd_user_dir=tmp_path / "systemd-user",
        runner=lambda cmd, **kwargs: calls.append(list(cmd)) or subprocess.CompletedProcess(cmd, 0, stdout="", stderr=""),
        which=lambda name: f"/usr/bin/{name}" if name == "systemctl" else None,
    )

    result = autoupdate.ensure_default_autoupdate(
        plugin_dir=plugin_dir,
        hermes_home=hermes_home,
        systemd_user_dir=tmp_path / "systemd-user",
        runner=lambda cmd, **kwargs: calls.append(list(cmd)) or subprocess.CompletedProcess(cmd, 0, stdout="", stderr=""),
        which=lambda name: f"/usr/bin/{name}" if name == "systemctl" else None,
    )

    assert result["enabled"] is False
    assert result["installed"] is False
    assert result["reason"] == "disabled"


def test_non_git_install_skips_default_auto_install(tmp_path):
    plugin_dir = tmp_path / "plugins" / "adtention"
    plugin_dir.mkdir(parents=True)

    result = autoupdate.ensure_default_autoupdate(
        plugin_dir=plugin_dir,
        hermes_home=tmp_path / "home",
        systemd_user_dir=tmp_path / "systemd-user",
        runner=lambda cmd, **kwargs: subprocess.CompletedProcess(cmd, 0, stdout="", stderr=""),
        which=lambda name: f"/usr/bin/{name}" if name == "systemctl" else None,
    )

    assert result["enabled"] is True
    assert result["installed"] is False
    assert result["reason"] == "not_git_checkout"
