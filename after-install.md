# ADtention for Hermes installed

ADtention adds one quiet sponsor line to Telegram/Discord wait-state messages only. It never decorates final answers and never sends standalone ads.

Restart the Hermes gateway so the plugin is loaded:

```bash
hermes gateway restart
```

Then open Telegram or Discord and run:

```text
/adtention status
/adtention referral
/adtention privacy
```

Turn it off anytime:

```text
/adtention off
```

ADtention also installs a daily plugin auto-updater by default for git checkouts. Disable it anytime:

```text
/adtention autoupdate off
```

Remove it completely with:

```bash
hermes plugins remove adtention
hermes gateway restart
```
