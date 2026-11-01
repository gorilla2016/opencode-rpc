# opencode-rpc

Discord Rich Presence for [opencode](https://opencode.ai). Zero runtime dependencies — Python standard library only.

Shows what the agent is actually doing, live:

```
Watching opencode
Working in IDA decompiling
Running: npm test · deepseek-v4.1-flash · 142.5k output tokens
```

- `Running: <command>` for shell/exec tools
- `Editing <file>` / `Reading <file>` for file tools
- `Searching <pattern>`, `Delegating: <task>`, `Fetching <url>`
- `Using <tool>` for anything else (MCP tools included)
- `Thinking` / `Responding` between tool calls
- animated mascot per state (idle / working / thinking / error / done)
- elapsed timer for the current turn
- optional custom title, privacy mode, autostart

## How it works

It reads opencode's local SQLite store **read-only** (`%USERPROFILE%\.local\share\opencode\opencode.db`):
`session` (title, model, tokens, timestamps), `part` (the newest tool call + its input), and `message` (last user turn for the timer). Nothing is written to the DB, and no telemetry is sent anywhere except Discord's local IPC pipe.

## Requirements

- Windows (uses Discord's named pipe `\\.\pipe\discord-ipc-*`)
- Python 3.8+
- Discord **Desktop** running (browser Discord has no IPC)

## Run

```bat
run-opencode-rpc.cmd
```

or silently (no console):

```bat
run-opencode-rpc-hidden.vbs
```

One-shot test:

```bat
python opencode-rpc.py --once
```

Install login autostart:

```bat
install-autostart.cmd
```

Remove it:

```bat
uninstall-autostart.cmd
```

## Config

Created at `%USERPROFILE%\.opencode-rpc\config.json`:

| Key | Meaning |
|---|---|
| `client_id` | Discord application ID. Default reuses the public codex-rpc app. |
| `activity_name` | Activity name shown above the card (e.g. `opencode`). |
| `title_override` | Overrides the "Working in …" text. Empty = real session title. |
| `large_image` | Force one image (asset key or public HTTPS URL) for all states. |
| `assets` | Per-state mascot URLs: `idle`, `working`, `thinking`, `error`, `done`. |
| `large_text` | Hover text for the image. |
| `update_interval` | Seconds between DB polls. |
| `resend_interval` | Seconds between presence re-pushes. |
| `active_window` | Seconds of inactivity before the card shows `Idle`. |
| `show_tokens` | Include model + output tokens. |
| `privacy` | `public` shows the session title; `private` shows "a project". |
| `detail_level` | `minimal` (default) shows actions/tool names only; `normal` adds program/file names; `full` shows the actual command/pattern/url (leaks details). |
| `db_path` | Override the opencode DB path. |

### Make it say "opencode" with your own logo

The default app ID belongs to codex-rpc, so Discord may label the card with that app's name. To use your own:

1. Create an app at https://discord.com/developers/applications named **opencode**.
2. Upload an image asset (e.g. key `opencode`).
3. Set `"client_id": "<your app id>"` and `"large_image": "opencode"` in the config.

Or host an animated GIF anywhere public and put its URL in `large_image` / `assets`.

## Mascot

`make_mascot.py` generates the animated terminal-creature GIFs in `assets/` and uploads them (to catbox by default) so Discord can fetch them as external assets. The generated `assets/*.gif` are included in this repo.

## License

MIT — see [LICENSE](LICENSE).
