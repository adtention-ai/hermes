"""Default-on auto-update installer for the ADtention Hermes plugin.

The plugin updater is deliberately small and fail-closed: it only updates git
checkouts, only pulls fast-forward changes, skips dirty trees, and restarts the
Hermes gateway only when the plugin SHA actually changes.
"""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
from pathlib import Path
from typing import Any, Callable

SERVICE_NAME = "adtention-autoupdate.service"
TIMER_NAME = "adtention-autoupdate.timer"
SCRIPT_NAME = "adtention-autoupdate.sh"
DISABLED_SENTINEL = "autoupdate.disabled"
METHOD_SENTINEL = "autoupdate.method"
CRON_BEGIN = "# ADTENTION_AUTOUPDATE_BEGIN"
CRON_END = "# ADTENTION_AUTOUPDATE_END"

Runner = Callable[..., subprocess.CompletedProcess]
Which = Callable[[str], str | None]


def hermes_home() -> Path:
    try:
        from hermes_constants import get_hermes_home  # type: ignore

        return Path(get_hermes_home())
    except Exception:
        return Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes"))


def plugin_dir() -> Path:
    return Path(__file__).resolve().parent.parent


def default_systemd_user_dir() -> Path:
    return Path.home() / ".config" / "systemd" / "user"


def _state_dir(home: Path) -> Path:
    return home / "adtention"


def _disabled_path(home: Path) -> Path:
    return _state_dir(home) / DISABLED_SENTINEL


def _method_path(home: Path) -> Path:
    return _state_dir(home) / METHOD_SENTINEL


def _script_path(home: Path) -> Path:
    return _state_dir(home) / SCRIPT_NAME


def _record_install(home: Path, method: str) -> None:
    _state_dir(home).mkdir(parents=True, exist_ok=True)
    _method_path(home).write_text(f"{method}\n", encoding="utf-8")


def _clear_install_record(home: Path) -> None:
    try:
        _method_path(home).unlink()
    except FileNotFoundError:
        pass


def _recorded_method(home: Path) -> str | None:
    try:
        method = _method_path(home).read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return None
    return method if method in {"systemd", "crontab"} else None


def _runner(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, **kwargs)


def _which(name: str) -> str | None:
    return shutil.which(name)


def _auto_update_allowed(home: Path) -> tuple[bool, str | None]:
    env = os.environ.get("ADTENTION_AUTOUPDATE", "").strip().lower()
    if env in {"0", "false", "no", "off", "disabled"}:
        return False, "env_disabled"
    if _disabled_path(home).exists():
        return False, "disabled"
    return True, None


def _completed(ok: bool, **fields: Any) -> dict[str, Any]:
    result = {"ok": ok}
    result.update(fields)
    return result


def updater_script(plugin_path: Path, home: Path) -> str:
    plugin_q = shlex.quote(str(plugin_path))
    home_q = shlex.quote(str(home))
    return f"""#!/usr/bin/env bash
set -euo pipefail

if [ -z "${{HERMES_HOME:-}}" ]; then
  export HERMES_HOME={home_q}
else
  export HERMES_HOME
fi
if [ -z "${{ADTENTION_PLUGIN_DIR:-}}" ]; then
  PLUGIN_DIR={plugin_q}
else
  PLUGIN_DIR="$ADTENTION_PLUGIN_DIR"
fi
LOG_DIR="$HERMES_HOME/logs"
STATE_DIR="$HERMES_HOME/adtention"
LOG_FILE="$LOG_DIR/adtention-autoupdate.log"
LOCK_DIR="$STATE_DIR/autoupdate.lock"

mkdir -p "$LOG_DIR" "$STATE_DIR"

{{
  echo "[$(date -u +'%Y-%m-%dT%H:%M:%SZ')] ADtention auto-update start"

  if ! mkdir "$LOCK_DIR" 2>/dev/null; then
    echo "Another ADtention auto-update is already running; skipping."
    exit 0
  fi
  trap 'rmdir "$LOCK_DIR" 2>/dev/null || true' EXIT

  if [ ! -d "$PLUGIN_DIR/.git" ]; then
    echo "Plugin is not a git checkout; skipping."
    exit 0
  fi
  cd "$PLUGIN_DIR"

  remote_url="$(git remote get-url origin 2>/dev/null || true)"
  case "$remote_url" in
    git@github.com:adtention-ai/hermes.git|ssh://git@github.com/adtention-ai/hermes.git|https://github.com/adtention-ai/hermes.git|https://github.com/adtention-ai/hermes)
      ;;
    *)
      echo "Unexpected ADtention plugin remote '$remote_url'; skipping."
      exit 0
      ;;
  esac

  if [ -n "$(git status --porcelain --untracked-files=normal)" ]; then
    echo "Plugin checkout has local changes; skipping auto-update."
    exit 0
  fi

  old_sha="$(git rev-parse HEAD)"
  current_branch="$(git branch --show-current 2>/dev/null || true)"
  if [ -z "$current_branch" ]; then
    echo "Plugin checkout is detached from a branch; skipping auto-update."
    exit 0
  fi
  git pull --ff-only origin "$current_branch"
  new_sha="$(git rev-parse HEAD)"

  if [ "$old_sha" != "$new_sha" ]; then
    echo "Updated ADtention plugin: $old_sha -> $new_sha"
    if command -v hermes >/dev/null 2>&1; then
      hermes gateway restart || true
    fi
  else
    echo "ADtention plugin already up to date."
  fi
}} >>"$LOG_FILE" 2>&1
"""


def write_updater_script(*, plugin_dir: Path, hermes_home: Path) -> Path:
    _state_dir(hermes_home).mkdir(parents=True, exist_ok=True)
    script = _script_path(hermes_home)
    script.write_text(updater_script(plugin_dir, hermes_home), encoding="utf-8")
    script.chmod(0o755)
    return script


def _systemd_quote(value: object) -> str:
    text = str(value)
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _path_env() -> str:
    return os.environ.get("PATH") or "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"


def _systemd_service(script: Path, home: Path, plugin_path: Path) -> str:
    return f"""[Unit]
Description=ADtention Hermes plugin auto-update
Documentation=https://github.com/adtention-ai/hermes

[Service]
Type=oneshot
Environment={_systemd_quote(f"HERMES_HOME={home}")}
Environment={_systemd_quote(f"ADTENTION_PLUGIN_DIR={plugin_path}")}
Environment={_systemd_quote(f"PATH={_path_env()}")}
ExecStart={_systemd_quote(script)}
"""


def _systemd_timer() -> str:
    return """[Unit]
Description=Daily ADtention Hermes plugin auto-update

[Timer]
OnCalendar=*-*-* 04:17:00
Persistent=true
RandomizedDelaySec=2h
Unit=adtention-autoupdate.service

[Install]
WantedBy=timers.target
"""


def _install_systemd_timer(
    *,
    script: Path,
    home: Path,
    plugin_path: Path,
    systemd_user_dir: Path,
    runner: Runner,
    which: Which,
) -> dict[str, Any]:
    systemctl = which("systemctl")
    if not systemctl:
        return _completed(False, reason="systemctl_missing")
    systemd_user_dir.mkdir(parents=True, exist_ok=True)
    (systemd_user_dir / SERVICE_NAME).write_text(_systemd_service(script, home, plugin_path), encoding="utf-8")
    (systemd_user_dir / TIMER_NAME).write_text(_systemd_timer(), encoding="utf-8")
    for cmd in (
        [systemctl, "--user", "daemon-reload"],
        [systemctl, "--user", "enable", "--now", TIMER_NAME],
    ):
        result = runner(cmd, capture_output=True, text=True, timeout=15)
        if result.returncode != 0:
            return _completed(False, reason="systemctl_failed", stderr=(result.stderr or result.stdout or "").strip())
    return _completed(True, method="systemd")


def _strip_cron_block(text: str) -> str:
    lines = text.splitlines()
    output: list[str] = []
    skipping = False
    for line in lines:
        if line.strip() == CRON_BEGIN:
            skipping = True
            continue
        if line.strip() == CRON_END:
            skipping = False
            continue
        if not skipping:
            output.append(line)
    return "\n".join(output).strip()


def _install_crontab(*, script: Path, home: Path, plugin_path: Path, runner: Runner, which: Which) -> dict[str, Any]:
    crontab = which("crontab")
    if not crontab:
        return _completed(False, reason="crontab_missing")
    existing_result = runner([crontab, "-l"], capture_output=True, text=True, timeout=15)
    existing = existing_result.stdout if existing_result.returncode == 0 else ""
    preserved = _strip_cron_block(existing)
    line = (
        "17 4 * * * "
        f"HERMES_HOME={shlex.quote(str(home))} "
        f"ADTENTION_PLUGIN_DIR={shlex.quote(str(plugin_path))} "
        f"PATH={shlex.quote(_path_env())} "
        f"{shlex.quote(str(script))}"
    )
    block = f"{CRON_BEGIN}\n{line}\n{CRON_END}"
    new_cron = f"{preserved}\n{block}\n" if preserved else f"{block}\n"
    result = runner([crontab, "-"], input=new_cron, capture_output=True, text=True, timeout=15)
    if result.returncode != 0:
        return _completed(False, reason="crontab_failed", stderr=(result.stderr or result.stdout or "").strip())
    return _completed(True, method="crontab")


def ensure_default_autoupdate(
    *,
    plugin_dir: Path | None = None,
    hermes_home: Path | None = None,
    systemd_user_dir: Path | None = None,
    runner: Runner = _runner,
    which: Which = _which,
) -> dict[str, Any]:
    """Ensure daily auto-update is installed unless the user disabled it."""
    home = Path(hermes_home) if hermes_home is not None else globals()["hermes_home"]()
    plug = Path(plugin_dir) if plugin_dir is not None else globals()["plugin_dir"]()
    allowed, reason = _auto_update_allowed(home)
    if not allowed:
        return {"enabled": False, "installed": False, "reason": reason, "method": "disabled"}
    if not (plug / ".git").exists():
        return {"enabled": True, "installed": False, "reason": "not_git_checkout", "method": "none"}

    script = write_updater_script(plugin_dir=plug, hermes_home=home)
    _clear_install_record(home)
    systemd_result = _install_systemd_timer(
        script=script,
        home=home,
        plugin_path=plug,
        systemd_user_dir=Path(systemd_user_dir) if systemd_user_dir is not None else default_systemd_user_dir(),
        runner=runner,
        which=which,
    )
    if systemd_result.get("ok"):
        _record_install(home, "systemd")
        return {"enabled": True, "installed": True, "method": "systemd", "script": str(script)}

    cron_result = _install_crontab(script=script, home=home, plugin_path=plug, runner=runner, which=which)
    if cron_result.get("ok"):
        _record_install(home, "crontab")
        return {"enabled": True, "installed": True, "method": "crontab", "script": str(script)}

    return {
        "enabled": True,
        "installed": False,
        "method": "none",
        "reason": cron_result.get("reason") or systemd_result.get("reason") or "install_failed",
    }


def autoupdate_status(
    *,
    hermes_home: Path | None = None,
    systemd_user_dir: Path | None = None,
    runner: Runner = _runner,
    which: Which = _which,
) -> dict[str, Any]:
    home = Path(hermes_home) if hermes_home is not None else globals()["hermes_home"]()
    allowed, reason = _auto_update_allowed(home)
    if not allowed:
        return {"enabled": False, "installed": False, "reason": reason, "method": "disabled"}

    script = _script_path(home)
    method = _recorded_method(home)
    user_dir = Path(systemd_user_dir) if systemd_user_dir is not None else default_systemd_user_dir()

    if method == "systemd":
        service = user_dir / SERVICE_NAME
        timer = user_dir / TIMER_NAME
        if not (script.exists() and service.exists() and timer.exists()):
            return {"enabled": True, "installed": False, "method": "none", "script": str(script)}
        systemctl = which("systemctl")
        if systemctl:
            result = runner([systemctl, "--user", "is-enabled", TIMER_NAME], capture_output=True, text=True, timeout=15)
            if result.returncode != 0:
                return {
                    "enabled": True,
                    "installed": False,
                    "method": "none",
                    "reason": "systemd_not_enabled",
                    "script": str(script),
                }
        return {"enabled": True, "installed": True, "method": "systemd", "script": str(script)}

    if method == "crontab":
        if not script.exists():
            return {"enabled": True, "installed": False, "method": "none", "script": str(script)}
        crontab = which("crontab")
        if crontab:
            result = runner([crontab, "-l"], capture_output=True, text=True, timeout=15)
            if result.returncode != 0 or CRON_BEGIN not in result.stdout or CRON_END not in result.stdout:
                return {
                    "enabled": True,
                    "installed": False,
                    "method": "none",
                    "reason": "crontab_block_missing",
                    "script": str(script),
                }
        return {"enabled": True, "installed": True, "method": "crontab", "script": str(script)}

    return {"enabled": True, "installed": False, "method": "none", "script": str(script)}


def enable_autoupdate(
    *,
    plugin_dir: Path | None = None,
    hermes_home: Path | None = None,
    systemd_user_dir: Path | None = None,
    runner: Runner = _runner,
    which: Which = _which,
) -> dict[str, Any]:
    home = Path(hermes_home) if hermes_home is not None else globals()["hermes_home"]()
    disabled = _disabled_path(home)
    if disabled.exists():
        disabled.unlink()
    return ensure_default_autoupdate(
        plugin_dir=plugin_dir,
        hermes_home=home,
        systemd_user_dir=systemd_user_dir,
        runner=runner,
        which=which,
    )


def disable_autoupdate(
    *,
    hermes_home: Path | None = None,
    systemd_user_dir: Path | None = None,
    runner: Runner = _runner,
    which: Which = _which,
) -> dict[str, Any]:
    home = Path(hermes_home) if hermes_home is not None else globals()["hermes_home"]()
    _state_dir(home).mkdir(parents=True, exist_ok=True)
    _disabled_path(home).write_text("disabled\n", encoding="utf-8")
    _clear_install_record(home)

    systemctl = which("systemctl")
    user_dir = Path(systemd_user_dir) if systemd_user_dir is not None else default_systemd_user_dir()
    if systemctl:
        for cmd in (
            [systemctl, "--user", "disable", "--now", TIMER_NAME],
            [systemctl, "--user", "daemon-reload"],
        ):
            try:
                runner(cmd, capture_output=True, text=True, timeout=15)
            except Exception:
                pass
    for filename in (SERVICE_NAME, TIMER_NAME):
        try:
            (user_dir / filename).unlink()
        except FileNotFoundError:
            pass

    crontab = which("crontab")
    if crontab:
        try:
            existing_result = runner([crontab, "-l"], capture_output=True, text=True, timeout=15)
            existing = existing_result.stdout if existing_result.returncode == 0 else ""
            stripped = _strip_cron_block(existing)
            runner([crontab, "-"], input=(stripped + "\n") if stripped else "", capture_output=True, text=True, timeout=15)
        except Exception:
            pass

    return {"enabled": False, "installed": False, "method": "disabled", "reason": "disabled"}
