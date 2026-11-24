<div align="center">

# cursor-reset

**Local developer tool: inspect and rotate machine identifiers used by VS Code–family editors.**

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

**Zero dependencies · One file · macOS / Windows / Linux**

</div>

---

## What it does

VS Code–based editors (including Cursor) generate per-install device
identifiers in `storage.json`, `state.vscdb`, and the application's
`main.js`. Developers working with multiple test environments, CI
sandboxes, or reproducible-install research need to inspect, back up,
and regenerate these identifiers.

`cursor-reset` does exactly that — with full backups and a one-command
restore:

| Command | What happens |
|---|---|
| `status` | Shows current identifiers, app version, backups (read-only) |
| `reset` | Backup → regenerate identifiers → verify → done |
| `usage` | Query the editor's own usage endpoint for your account (your cookie, your machine) |
| `extend` | Adjust a client-side display constant (backed up) |
| `pin-update` | Disable the app's auto-updater |
| `verify` | Health check: identifiers present and well-formed |
| `restore` | Restore previous state from backup |
| `watch` | Monitor identifier changes and log them |

## Quick start

```bash
git clone https://github.com/Awaisdev01/cursor-reset.git
cd cursor-reset
python3 cursor_reset.py status
python3 cursor_reset.py reset    # backs up first
```

Interactive menu: run `python3 cursor_reset.py` with no arguments.

macOS desktop build: `./build_mac.sh` → `dist/cursor-reset.dmg`

## How the identifiers work

| Where | What | Format |
|---|---|---|
| `storage.json` | `telemetry.machineId`, `macMachineId` | 64-char hex |
| | `telemetry.sqmId` | `{GUID}` |
| | `telemetry.devDeviceId` | UUID |
| `state.vscdb` (sqlite) | same 5 keys | — |
| `out/main.js` | identifier generation function | patched structurally |

Regenerated identifiers match each field's expected format exactly.
Patches carry `/*v1*/`…`/*v4*/` sentinels so re-runs detect previous
patches and re-apply cleanly after app updates.

## Safety

- Everything is backed up before any change
- `restore` undoes changes in one command
- Login data is never touched
- ID formats are CI-asserted on every push

## License

MIT — see [LICENSE](LICENSE).
