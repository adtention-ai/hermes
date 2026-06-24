"""Gateway command handling for /adtention."""

from __future__ import annotations

HELP = """ADtention commands:
/adtention status — show enabled state, balance, category, and current sponsor
/adtention on — enable wait-state sponsor segments
/adtention off — disable wait-state sponsor segments
/adtention privacy — explain what leaves your machine
/adtention sponsor — show the current sponsor
""".strip()

PRIVACY_TEXT = (
    "ADtention for Hermes classifies locally. Prompts, replies, chat history, code, files, "
    "filenames, paths, chat IDs, user IDs, tool arguments, terminal output, and tool output "
    "never leave this machine. The API receives only broad category words, pseudonymous "
    "install/publisher IDs, host/surface/platform labels, client/version labels, render "
    "nonces, and impression/creative IDs for successful render acknowledgment."
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

    if subcommand == "sponsor":
        sponsor = (_status(runtime).get("sponsor") or {})
        if not sponsor:
            return "No sponsor is currently cached."
        text = sponsor.get("text", "Current sponsor")
        url = sponsor.get("click_url", "")
        return f"Current sponsor: {text}" + (f" → {url}" if url else "")

    return HELP
