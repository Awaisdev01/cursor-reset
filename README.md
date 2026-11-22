<div align="center">

# 🔄 cursor-reset

**Survive Cursor trial limits on one machine.**

Rotates every device identifier Cursor keys its trial limit on —
machineId, macMachineId, sqmId, devDeviceId, serviceMachineId — across
`storage.json`, `state.vscdb`, and Cursor's `out/main.js`.

Backup-first · verified-after · idempotent · survives Cursor updates
(multi-strategy patching with version-aware fallbacks)

**Zero dependencies · Python 3.8+ · macOS / Windows / Linux**

[![CI](https://github.com/awaisdev5765/cursor-reset/actions/workflows/ci.yml/badge.svg)](https://github.com/awaisdev5765/cursor-reset/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

[![Install](https://img.shields.io/badge/install-curl_|_bash-8b5cf6)](#install)

</div>

---

```bash
$ python3 cursor_reset.py status
Cursor install: /Applications/Cursor.app/Contents/Resources/app
Cursor version: 3.30.14

  telemetry.machineId       3e963c0154b46764dbaecf507454372d091575fee440
  telemetry.macMachineId    0b93d7adac7b95ad5dbb3b59ac616c51384d916bd310
  telemetry.sqmId           {2750EC91-E465-4714-907F-602DC4C9F464}
  telemetry.devDeviceId     f0ec4fe1-323a-47f2-aa52-a93b7ebf17c9

$ python3 cursor_reset.py reset
✓ storage.json: 5 IDs rotated
✓ state.vscdb: 5 IDs rotated
✓ main.js: 4 spots patched (backup: main.js.20261123-030228.bak)
✓ done — restart Cursor to apply.
```

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/awaisdev5765/cursor-reset/main/install.sh | bash
```

Installs `cursor_reset.py` to `~/.cursor-reset/` and adds a `cursor-reset`
alias. Or just download `cursor_reset.py` — it's one file.

## Commands

| Command | What it does |
|---|---|
| `status` | Show current device IDs, Cursor version, last backup |
| `reset` | Backup → rotate all IDs in storage.json + state.vscdb → patch main.js → verify |
| `verify` | Confirm IDs present + patch markers valid (exit 0/1) |
| `restore` | Restore main.js from the latest backup |

## Why this one survives Cursor updates

The 3.3M-line `main.js` gets patched at **4 independent spots**, each
matched by structure, not exact minified names:

1. **machineId function** — the `sha256(mac-address).digest("hex")` function body
2. **MAC address getter** — the `Unable to retrieve mac address` fallback
3. **Windows sqmId** — the `GetStringRegKey("HKEY_LOCAL_MACHINE"...MachineId)` lookup
4. **deviceId** — the `vscode/deviceid").getDeviceId()` call

Each replacement is wrapped in sentinel markers (`/*v1*/`…`/*v4*/`) so
repeat runs detect and re-patch cleanly. If a Cursor update renames
minified internals (they all contain `$` and change weekly), the
storage.json + state.vscdb rotation still works — main.js patching is the
second layer of defense, not the only one.

Generated IDs match Cursor's expected formats exactly: 64-char sha256 hex
for machine IDs, `{GUID}` for sqmId, plain UUIDs for device IDs.

## Safety

- **Backup before every patch** — `globalStorage/cursor-reset-backups/main.js.*.bak`
- **`restore`** returns main.js to the pre-patch state in one command
- **storage.json / state.vscdb are never auto-restored** — your login lives there
- **`--dry-run`-style status first**: nothing is touched until you say `reset`

## FAQ

**Does this actually bypass the trial limit?**
It rotates the device-level identifiers Cursor's trial server keys on
(`You've reached your trial request limit` / `Too many free trial accounts
used on this machine`). If the limit is account-level, a fresh account is
the reliable path — that's Cursor's server-side design and no local tool
changes it.

**Will this get my account banned?**
Cursor's ToS prohibits evading usage limits. Use on your own machine, at
your own risk, for the trial-evaluation purpose. Don't use it to run a
free-account farm — that's both against ToS and what gets IP-level flags.

**Does it work after a Cursor update?**
That's the point. The structural patterns + multi-layer rotation keep
working where exact-match scripts break. If a strategy misses, `verify`
tells you which one and the other layers still rotate.

**What does it NOT do?**
No account creation, no email farming, no browser automation, no token
injection. One file, one job: device identity rotation on this machine.

## License

MIT — see [LICENSE](LICENSE).
