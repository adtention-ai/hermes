"""Gateway command handling for /adtention."""

from __future__ import annotations

HELP = """ADtention commands:
/adtention status — show enabled state, balance, category, and current sponsor
/adtention referral — show your referral link for inviting other Hermes users
/adtention on — enable wait-state sponsor segments
/adtention off — disable wait-state sponsor segments
/adtention privacy — explain what leaves your machine
/adtention sponsor — show the current sponsor
/adtention autoupdate status|on|off — daily plugin updates are enabled by default
""".strip()

PRIVACY_TEXT = (
    "ADtention for Hermes classifies locally. Prompts, replies, chat history, code, files, "
    "filenames, paths, chat IDs, user IDs, tool arguments, terminal output, and tool output "
    "never leave this machine. The API receives only broad category words, pseudonymous "
    "install/publisher IDs, host/surface/platform labels, client/version labels, optional "
    "referral codes, render nonces, and impression/creative IDs for successful render "
    "acknowledgment."
)


def _status(runtime) -> dict:
    if hasattr(runtime, "command_status"):
        return runtime.command_status()
    return {"enabled": runtime.is_enabled(), "balance_usd": None, "category_v2": "general", "sponsor": None}


def _set_enabled(runtime, enabled: bool) -> None:
    if hasattr(runtime, "set_enabled"):
        runtime.set_enabled(enabled)
    elif hasattr(runtime, "state"):
        runtime.state.set_enabled(enabled)


def _autoupdate_status(runtime) -> dict:
    if hasattr(runtime, "autoupdate_status"):
        return runtime.autoupdate_status()
    return {"enabled": True, "installed": False, "method": "unknown"}


def _referral_status(runtime) -> dict:
    if hasattr(runtime, "referral_status"):
        return runtime.referral_status()
    status = _status(runtime)
    referral = status.get("referral") if isinstance(status, dict) else None
    return referral if isinstance(referral, dict) else {}


def _format_referral_status(status: dict) -> str:
    code = str(status.get("referral_code") or "").strip()
    url = str(status.get("referral_url") or "").strip()
    if not code and not url:
        return (
            "ADtention referral link is not available yet. It appears after this install "
            "registers with the ADtention API."
        )
    if not url and code:
        url = f"https://adtention.ai/r/{code}"
    details = [f"Your ADtention referral link: {url}"]
    if code:
        details.append(f"Referral code: {code}")
    details.append("You earn 15% of referred publishers' ADtention impression earnings.")
    return "\n".join(details)


def _format_autoupdate_status(status: dict) -> str:
    enabled = bool(status.get("enabled"))
    state = "enabled" if enabled else "disabled"
    installed = "installed" if status.get("installed") else "not installed"
    method = status.get("method") or status.get("reason") or "unknown"
    text = f"ADtention auto-update is {state}; daily updater is {installed} ({method})."
    if enabled:
        text += " Disable with /adtention autoupdate off."
    else:
        text += " Re-enable with /adtention autoupdate on."
    return text


def handle_command(text: str, runtime) -> str:
    parts = (text or "").strip().split()
    if not parts or parts[0].lower() != "/adtention":
        return HELP
    subcommand = parts[1].lower() if len(parts) > 1 else "status"

    if subcommand == "status":
        status = _status(runtime)
        enabled = "enabled" if status.get("enabled") else "disabled"
        balance = status.get("balance_usd")
        balance_text = f"${balance:.2f}" if isinstance(balance, (int, float)) else "unknown"
        category = status.get("category_v2") or "general"
        sponsor = status.get("sponsor") or {}
        sponsor_text = sponsor.get("text", "none") if isinstance(sponsor, dict) else "none"
        return f"ADtention is {enabled}. Balance: {balance_text}. Category: {category}. Sponsor: {sponsor_text}."

    if subcommand == "off":
        _set_enabled(runtime, False)
        return "ADtention disabled. Wait-state sponsor segments will not be rendered."

    if subcommand == "on":
        _set_enabled(runtime, True)
        return "ADtention enabled. Wait-state sponsor segments may be rendered while Hermes works."

    if subcommand == "privacy":
        return PRIVACY_TEXT

    if subcommand in {"referral", "refer", "ref"}:
        return _format_referral_status(_referral_status(runtime))

    if subcommand == "sponsor":
        sponsor = (_status(runtime).get("sponsor") or {})
        if not sponsor:
            return "No sponsor is currently cached."
        text = sponsor.get("text", "Current sponsor")
        url = sponsor.get("click_url", "")
        return f"Current sponsor: {text}" + (f" → {url}" if url else "")

    if subcommand == "autoupdate":
        action = parts[2].lower() if len(parts) > 2 else "status"
        if action in {"status", "show"}:
            return _format_autoupdate_status(_autoupdate_status(runtime))
        if action in {"off", "disable", "disabled"}:
            if hasattr(runtime, "disable_autoupdate"):
                return _format_autoupdate_status(runtime.disable_autoupdate())
            return "ADtention auto-update could not be disabled on this Hermes version."
        if action in {"on", "enable", "enabled"}:
            if hasattr(runtime, "enable_autoupdate"):
                return _format_autoupdate_status(runtime.enable_autoupdate())
            return "ADtention auto-update could not be enabled on this Hermes version."
        return HELP

    return HELP
