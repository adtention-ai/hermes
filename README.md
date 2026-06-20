# ADtention for Hermes

**The wait-state sponsor line that pays you while your agent works.**

ADtention for Hermes is a standalone Hermes Agent plugin that decorates Telegram and Discord wait-state/status messages with a quiet sponsor segment. It works without a NousResearch core PR by running in compatibility mode: the plugin wraps live gateway adapter delivery methods and only modifies recognized wait-state messages such as `⏳ Working — 3 min`.

It never decorates final assistant answers and never sends standalone ad messages.

## Install

```bash
hermes plugins install adtention-ai/hermes --enable
hermes gateway restart
```

Then check status from Telegram or Discord:

```text
/adtention status
```

## Commands

```text
/adtention status   show enabled state, balance, category, and current sponsor
/adtention on       enable wait-state sponsor segments
/adtention off      disable wait-state sponsor segments
/adtention privacy  explain what leaves your machine
/adtention sponsor  show the current sponsor
```

## Privacy

ADtention for Hermes classifies locally. It **never sends prompts**, replies, chat history, code, files, filenames, paths, repo names, chat IDs, user IDs, tool arguments, terminal output, or tool output.

The API receives only broad metadata:

```json
{
  "publisher_id": "pub_...",
  "category": "data",
  "category_v2": "web_research",
  "host": "hermes",
  "surface": "hermes_wait_state",
  "platform": "telegram",
  "nonce": "render_..."
}
```

Impressions are acknowledged only after a wait-state message is successfully sent or edited.

## How it works

- `pre_gateway_dispatch` wraps Telegram/Discord gateway adapters once per process.
- `pre_llm_call` and tool hooks classify broad task intent locally.
- Sponsor fetches happen in the background, never in the render hot path.
- The renderer appends a single bounded line with an `⊕ ADtention ·` marker.
- Message edits replace the plugin’s previous segment instead of duplicating it.
- Broken ADtention API calls are isolated from normal Hermes message delivery.

## Configuration

Optional environment variables:

```bash
export ADTENTION_PUBLISHER_ID="pub_..."
export ADTENTION_API_URL="https://api.adtention.ai"
```

The plugin stores local state under the active Hermes profile home, in `adtention/`.

## Update / disable / remove

```bash
hermes plugins update adtention
hermes plugins disable adtention
hermes plugins remove adtention
hermes gateway restart
```

## Development

```bash
python -m pytest tests -q
python -m compileall adtention_hermes
```

The v1 implementation is stdlib-only at runtime.
