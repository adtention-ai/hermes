from __future__ import annotations

import subprocess
import os
from pathlib import Path

from adtention_hermes import autoupdate


def _git_plugin(tmp_path: Path) -> Path:
    plugin_dir = tmp_path / "plugins" / "adtention"
    (plugin_dir / ".git").mkdir(parents=True)
    return plugin_dir


def _write_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


def _run_generated_script(script: Path, *, home: Path, plugin_dir: Path, bin_dir: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [str(script)],
        env={
            "PATH": f"{bin_dir}:{os.environ.get('PATH', '')}",
            "HERMES_HOME": str(home),
            "ADTENTION_PLUGIN_DIR": str(plugin_dir),
        },
        capture_output=True,
        text=True,
        timeout=30,
    )


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
    script_text = script.read_text()
    assert "hermes plugins update adtention" not in script_text
    assert "git pull --ff-only" in script_text
    assert "hermes gateway restart" in script_text
    assert "git status --porcelain --untracked-files=normal" in script_text
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


def test_generated_updater_rejects_malicious_remote_suffix(tmp_path):
    plugin_dir = _git_plugin(tmp_path)
    hermes_home = tmp_path / "home"
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    git_calls = tmp_path / "git-calls.log"
    _write_executable(
        bin_dir / "git",
        f"""#!/usr/bin/env bash
echo "$*" >> {git_calls}
case "$*" in
  "remote get-url origin") echo "https://evil.tld/github.com/adtention-ai/hermes.git" ;;
  "status --porcelain --untracked-files=normal") ;;
  "rev-parse HEAD") echo "same-sha" ;;
  "pull --ff-only"*) echo PULLED >> {git_calls} ;;
esac
""",
    )
    script = autoupdate.write_updater_script(plugin_dir=plugin_dir, hermes_home=hermes_home)

    result = _run_generated_script(script, home=hermes_home, plugin_dir=plugin_dir, bin_dir=bin_dir)

    assert result.returncode == 0
    assert "Unexpected ADtention plugin remote" in (hermes_home / "logs" / "adtention-autoupdate.log").read_text()
    assert "PULLED" not in git_calls.read_text()


def test_generated_updater_skips_untracked_dirty_checkout(tmp_path):
    plugin_dir = _git_plugin(tmp_path)
    hermes_home = tmp_path / "home"
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    git_calls = tmp_path / "git-calls.log"
    _write_executable(
        bin_dir / "git",
        f"""#!/usr/bin/env bash
echo "$*" >> {git_calls}
case "$*" in
  "remote get-url origin") echo "https://github.com/adtention-ai/hermes.git" ;;
  "status --porcelain --untracked-files=normal") echo "?? scratch.txt" ;;
  "rev-parse HEAD") echo "same-sha" ;;
  "pull --ff-only"*) echo PULLED >> {git_calls} ;;
esac
""",
    )
    script = autoupdate.write_updater_script(plugin_dir=plugin_dir, hermes_home=hermes_home)

    result = _run_generated_script(script, home=hermes_home, plugin_dir=plugin_dir, bin_dir=bin_dir)

    assert result.returncode == 0
    assert "Plugin checkout has local changes" in (hermes_home / "logs" / "adtention-autoupdate.log").read_text()
    assert "PULLED" not in git_calls.read_text()


def test_systemd_failure_does_not_report_installed_from_leftover_unit_files(tmp_path):
    plugin_dir = _git_plugin(tmp_path)
    hermes_home = tmp_path / "home"
    systemd_dir = tmp_path / "systemd-user"

    def runner(cmd, **_kwargs):
        if "enable" in cmd:
            return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="no user bus")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    install_result = autoupdate.ensure_default_autoupdate(
        plugin_dir=plugin_dir,
        hermes_home=hermes_home,
        systemd_user_dir=systemd_dir,
        runner=runner,
        which=lambda name: "/usr/bin/systemctl" if name == "systemctl" else None,
    )

    status = autoupdate.autoupdate_status(
        hermes_home=hermes_home,
        systemd_user_dir=systemd_dir,
        runner=runner,
        which=lambda name: "/usr/bin/systemctl" if name == "systemctl" else None,
    )

    assert install_result["installed"] is False
    assert (systemd_dir / "adtention-autoupdate.timer").exists()
    assert status["installed"] is False
    assert status["method"] == "none"
