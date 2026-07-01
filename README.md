# ADtention for Hermes

**The Hermes wait-state sponsor line that pays you while your agent works.**

You already watch Telegram and Discord “⏳ Working” updates while Hermes handles a request. ADtention adds one quiet sponsor line to those wait-state messages and shows your running balance next to it.

```text
⏳ Working — 3 min
$0.42 · Neon: Postgres for AI agents → More Info
```

One line. No popups. No standalone ads. No final-answer ads. No signup to earn. And **no prompts, code, chat IDs, tool arguments, terminal output, or tool output ever leave your machine**.

> **Telegram and Discord wait states only.** ADtention appears only on recognized Hermes status bubbles such as `⏳ Working`, `Still working`, or `Processing`. It does not modify final assistant answers, tool/debug progress, terminal output, or unsupported surfaces.

---

## “Wait. Ads in my assistant chat? Hard pass.”

Good instinct. Read this part first, then decide.

ADtention for Hermes classifies the current turn **locally** into one broad task bucket — for example `coding`, `devops`, `data_ai`, `web_research`, `browser_scraping`, `productivity`, `creative_media`, `github`, `business_research`, `web3`, `smart_home`, or `general`.

The API receives only that bucket plus pseudonymous install/render metadata so it can pick a relevant sponsor and credit your balance. Your message content, code, files, chat identifiers, and tool outputs are not sent. Put plainly: it never sends prompts, replies, code, chat IDs, or tool output.

| Leaves your machine | Never leaves your machine |
| --- | --- |
| Broad category words such as `web` and `web_research` | Prompts, replies, or chat history |
| Random install/publisher ID | Code, files, filenames, paths, or repo names |
| Host/surface/platform labels such as `hermes_wait_state` and `telegram` | Chat IDs or user IDs |
| Render nonce, client tag, and client version | Tool arguments, terminal output, or tool output |
| Optional referral code if configured or requested | Copied referral-link query strings; they are normalized locally |
| Impression/creative IDs when a wait-state render is acknowledged | Account, email, or payout details just to install or earn |

**No account, email, or login is required to install or earn.** The install ID is a random local pseudonym. Cashing out, once available, will require an account with a payout method — but earning does not.

**Don’t take our word for it.** The outbound payload keys are allowlisted in [`adtention_hermes/client.py`](adtention_hermes/client.py), wait-state rendering is isolated in [`adtention_hermes/renderer.py`](adtention_hermes/renderer.py), and privacy behavior is covered by [`tests/test_client_privacy.py`](tests/test_client_privacy.py).

---

## What you actually get

- **A balance worth watching**: your running ADtention credit shown in the wait-state sponsor line.
- **Passive credit while Hermes works**: sponsors are eligible only while real Hermes work is happening.
- **Zero signup friction**: one install command, no account required to start earning.
- **Referral earning path**: `/adtention referral` shows your invite link, and referred installs can pass your code without exposing copied URL query strings.
- **Default daily updates**: installed git checkouts set up a daily ADtention plugin updater automatically, with an opt-out command if you want to manage updates yourself.
- **Privacy by architecture**: payload allowlists make accidental leakage fail closed.
- **A clean exit**: turn sponsor rendering off with `/adtention off`, disable auto-updates with `/adtention autoupdate off`, or disable/remove the plugin and restart the gateway.

---

## Install

```bash
hermes plugins install adtention-ai/hermes --enable
hermes gateway restart
```

Referred install:

```bash
ENV_PATH="$(hermes config env-path)" &&
mkdir -p "$(dirname "$ENV_PATH")" &&
{ grep -v '^ADTENTION_REFERRER=' "$ENV_PATH" 2>/dev/null || true; printf 'ADTENTION_REFERRER=h3r7vmj\n'; } > "$ENV_PATH.tmp" &&
mv "$ENV_PATH.tmp" "$ENV_PATH" &&
chmod 600 "$ENV_PATH" 2>/dev/null || true
hermes plugins install adtention-ai/hermes --enable
hermes gateway restart
```

Then check status from Telegram or Discord:

```text
/adtention status
/adtention referral
```

Share your referral link with other Hermes users. If you are installing from someone else’s link/code, persist `ADTENTION_REFERRER` before the first gateway restart so the registration is attributed:

```bash
ENV_PATH="$(hermes config env-path)" &&
mkdir -p "$(dirname "$ENV_PATH")" &&
{ grep -v '^ADTENTION_REFERRER=' "$ENV_PATH" 2>/dev/null || true; printf 'ADTENTION_REFERRER=h3r7vmj\n'; } > "$ENV_PATH.tmp" &&
mv "$ENV_PATH.tmp" "$ENV_PATH" &&
chmod 600 "$ENV_PATH" 2>/dev/null || true
hermes plugins install adtention-ai/hermes --enable
hermes gateway restart
```

The plugin reads `ADTENTION_REFERRER` / `ADTENTION_REFERRAL_URL`, normalizes copied links locally, and sends only the 7-character referral code as `ref` during registration.

ADtention installs a daily auto-updater by default when the plugin is a git checkout. It fast-forward pulls the plugin, skips dirty checkouts, and restarts the Hermes gateway only when the plugin SHA changes. Manage it from chat:

```text
/adtention autoupdate status
/adtention autoupdate off
/adtention autoupdate on
```

Want to inspect the privacy model from chat?

```text
/adtention privacy
```

---

## How the money works

- Sponsor fetches are locally rate-limited to **at most once every 15 seconds** and rendered credit is locally capped to **one sponsor impression per gateway turn**.
- Idle chats earn nothing. Leaving the gateway online overnight does not farm impressions.
- Rapid status edits do not duplicate credit; the plugin replaces its previous segment on edits and dedupes render acknowledgments by `impression_id`.
- An impression is acknowledged only after a decorated wait-state message is successfully sent or edited, then the cached sponsor is consumed so the same served impression is not reused.
- Cached sponsors expire quickly if they are not rendered.
- Tool/debug progress messages are not sponsored as billable wait states.
- Your balance accrues to the local install/publisher ID and is shown in the sponsor line.
- Referrers earn **15%** of referred publishers’ ADtention impression earnings; `/adtention referral` shows the local install’s share link once registered.
- Cashing out is coming: when it is available, you will create an account, attach a payout method, and withdraw past a threshold.

It is not a salary. It is beer money that shows up for work you were already doing.

---

## How it works under the hood

Two parts, deliberately kept separate so sponsor selection never blocks wait-state rendering:

- **The wait-state renderer uses a local cache.** Rendering a status bubble reads the latest cached sponsor and appends one bounded line. It does not fetch a sponsor in the hot path.
- **Register/serve happen in the background when Hermes work starts.** The plugin classifies broad task intent locally, gates sponsor refreshes to 15 seconds, calls the ADtention API once, and updates the cache for the next wait-state render.

The plugin runs in compatibility mode: it works without a Hermes core PR by wrapping Telegram/Discord gateway adapter send/edit methods at runtime. The wrapper only touches recognized wait-state/status text. Final assistant answers pass through unchanged.

Message edits replace the plugin’s previous line instead of stacking duplicate sponsor lines. Render acknowledgments happen only after a platform send/edit succeeds; they are best-effort, timeout-bounded, and caught so billing telemetry cannot break normal Hermes delivery. The client still is not a fraud boundary: the ADtention backend must keep impressions pending until a valid render acknowledgment, credit at most once per `impression_id`, and apply publisher/install/account/IP risk controls before payout.

---

## `/adtention`

```text
/adtention status   show enabled state, balance, category, and current sponsor
/adtention referral show your referral code/link for inviting other Hermes users
/adtention on       enable wait-state sponsor segments
/adtention off      disable wait-state sponsor segments
/adtention privacy  explain what leaves your machine
/adtention sponsor  show the current sponsor and link
/adtention autoupdate status|on|off  manage default daily plugin updates
```

The sponsor segment includes a visible `More Info` link when the platform supports links. `/adtention sponsor` prints the current sponsor and URL directly. `/adtention referral` prints the share link and code for the local publisher identity.

---

## Configuration

Optional environment variables:

```bash
export ADTENTION_PUBLISHER_ID="pub_..."
export ADTENTION_API_URL="https://api.adtention.ai"
export ADTENTION_REFERRER="h3r7vmj"       # referral attribution before first registration
export ADTENTION_REFERRAL_URL="https://adtention.ai/r/h3r7vmj"  # equivalent; normalized locally
export ADTENTION_AUTOUPDATE=0   # optional: prevent default daily updater setup
```

The plugin stores local state under the active Hermes profile home, in `adtention/`:

```text
~/.hermes/adtention/                         # default profile
~/.hermes/profiles/<profile>/adtention/      # named profiles
```

---

## Uninstall

Turn it off without removing the plugin:

```text
/adtention off
```

Turn off daily plugin auto-updates:

```text
/adtention autoupdate off
```

Disable or remove it completely:

```bash
hermes plugins disable adtention
hermes gateway restart

# or
hermes plugins remove adtention
hermes gateway restart
```

To also clear the local pseudonymous identity, cached sponsor, balance, and settings, delete the active profile’s `adtention/` state directory after disabling/removing the plugin.

---

## FAQ

**Is this an ad in my final answer?**
No. ADtention only decorates recognized wait-state/status bubbles. Final assistant answers are never modified.

**Does it send my prompts, chat IDs, or code?**
No. Classification happens locally. The API receives broad category metadata, pseudonymous install/render IDs, client/version labels, and nothing from your prompts, chat IDs, files, paths, tool arguments, terminal output, or tool output.

**Will it slow down Hermes?**
No. Sponsor fetches use a local cache and background refresh path. Render acknowledgments happen after a successful send/edit and are best-effort, timeout-bounded, and caught so Hermes can keep delivering messages normally.

**What happens if ADtention is offline?**
Hermes keeps working. The sponsor may not refresh, and wait-state messages may render without a sponsor segment.

**Do I need an account?**
Not to install or earn. Cashout, once available, will require an account with a payout method.

**Can I refer other Hermes users?**
Yes. Run `/adtention referral` to get your link/code. A referred install can set `ADTENTION_REFERRER` or `ADTENTION_REFERRAL_URL` before first registration; the plugin sends only the normalized code as `ref`.

**How do I know the plugin is active?**
Run `/adtention status` from Telegram or Discord.

**What if I hate it?**
Run `/adtention off`, or remove the plugin and restart the gateway. No account to close.

---

## Maintainers

### Development

```bash
python -m pytest tests -q
python -m compileall adtention_hermes
ruff check .
python -m build
```

The v1 implementation is stdlib-only at runtime.

### Release

Releases are cut automatically when a version bump lands on `main`. GitHub Actions creates the matching version tag, verifies the release, and publishes curated notes from [`CHANGELOG.md`](CHANGELOG.md).

1. Update the version in `pyproject.toml`, `plugin.yaml`, and the default client version in `adtention_hermes/client.py`.
2. Add a matching `CHANGELOG.md` section such as `## [0.1.1] - 2026-06-24`.
3. Run the full verification suite above.
4. Open and merge the PR into `main`.

The release workflow creates the `vX.Y.Z` tag on `main` merges. If that tag already exists, the workflow fails and asks for a version bump instead of overwriting an existing release. Manual tag and workflow-dispatch releases are still supported for maintainers.

---

Built by [ADtention](https://adtention.ai). Same network as the [OpenCode sponsor line](https://github.com/adtention-ai/opencode). MIT — see [LICENSE](LICENSE).
