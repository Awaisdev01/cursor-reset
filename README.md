<div align="center">

<img src="assets/cursor-logo.svg" width="72" alt="cursor-reset">

# cursor-reset

**Get more out of your Cursor trial — on one machine, automatically.**

[![CI](https://github.com/awaisdev5765/cursor-reset/actions/workflows/ci.yml/badge.svg)](https://github.com/awaisdev5765/cursor-reset/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![v0.3.0](https://img.shields.io/badge/version-0.3.0-blue)](https://github.com/awaisdev5765/cursor-reset/releases)

**Zero dependencies · One file · macOS / Windows / Linux**
**Terminal menu · Desktop .dmg/.exe · CI-grade safety**

[What it does](#-what-it-does) · [Quick start](#-quick-start) · [The 6 commands](#-the-6-commands) · [How it works](#-how-it-works-under-the-hood) · [Safety](#%EF%B8%8F-safety) · [FAQ](#-faq)

</div>

---

## 🎯 What it does

Cursor limits trial usage per **device**. When you hit
`You've reached your trial request limit` or
`Too many free trial accounts used on this machine` — that's Cursor's
server recognizing your machine by 5 hidden identifiers.

**cursor-reset rotates those identifiers**, so the server sees a fresh
machine. Plus:

| Feature | What it gives you |
|---|---|
| 🔄 **Device ID reset** | The core: rotate all 5 IDs across storage.json, state.vscdb, and main.js |
| 📊 **Usage check** | "premium: 137/150 — 13 left" — know *before* you hit the wall |
| 🧢 **Token cap extend** | Raise the client-side token limit so long chats keep going |
| 📌 **Version pin** | Disable auto-update so a Cursor update never wipes your patch |
| 👁️ **Watch mode** | Alerts the moment Cursor regenerates IDs (limit re-armed) |
| 🖥️ **Desktop app** | .dmg for Mac, .exe for Windows — click, don't type |

## 🚀 Quick start

**60-second path (any OS):**

```bash
# 1. get it
git clone https://github.com/awaisdev5765/cursor-reset.git
cd cursor-reset

# 2. look first (read-only, changes nothing)
python3 cursor_reset.py status

# 3. reset (backs up everything first, asks nothing else)
python3 cursor_reset.py reset

# 4. restart Cursor — done.
```

**Prefer the interactive menu?** Just run it with no arguments:

```bash
python3 cursor_reset.py
```

```
─── cursor-reset ───────────────────────────────
  1) Status                 Show device IDs, Cursor version, backups
  2) Reset device IDs       Rotate all IDs + patch main.js (backup first)
  3) Usage / limit check    Premium requests used vs max (needs web cookie)
  4) Extend token cap       Raise client-side token limit (backup first)
  5) Pin Cursor version     Disable auto-update so patches survive
  6) Verify patch health    Check IDs present + patch markers valid
  7) Restore main.js        Undo the last patch from backup
  8) Watch mode             Alert when Cursor regenerates device IDs
  9) Quit
  select [1-9]:
```

Press **2**, confirm with `y`, done. Press **8** to leave it watching —
it tells you the moment the limit re-arms.

**Prefer a window?** Download
[`cursor-reset.dmg`](https://github.com/awaisdev5765/cursor-reset/releases)
(macOS, 24MB) from Releases — drag to Applications, click Reset.
Windows: run `build_windows.ps1` once on a Windows machine to get the .exe.

## 📦 The 6 commands

Everything the menu does, from the CLI:

| Command | What happens | Risk |
|---|---|---|
| `status` | Shows your current 5 device IDs, Cursor version, last backup | none (read-only) |
| `reset` | Backup → rotate 5 IDs (storage.json + state.vscdb) → patch 4 spots in main.js → done | low (all backed up) |
| `usage` | Query Cursor for premium requests used/max. Local token is auto-attempted; for exact numbers paste your web cookie (see below) | none |
| `extend` | Raise the **client-side** token cap in workbench.js (e.g. `2e5` → `9e6`) so long chats don't hit the UI block | low (backed up) |
| `pin-update` | Remove `updateUrl` from product.json → Cursor stops auto-updating (and re-breaking the patch) | low |
| `verify` | Health check: IDs present + patch markers valid. Exit 1 if broken | none |
| `restore` | main.js back to pre-patch state from the newest backup | none |

**Getting exact usage numbers** — Cursor keeps the web session cookie in
your browser, not on disk (we tried: the local token is encrypted with the
macOS Keychain and the dashboard endpoint rejects it). One-time paste:

1. Open [cursor.com/dashboard](https://cursor.com/dashboard) in your browser
2. DevTools (`F12`) → Application → Cookies → `WorkosCursorSessionToken`
3. `python3 cursor_reset.py usage --token "<that value>"`

## 🔍 How it works (under the hood)

Cursor keys your trial on these identifiers:

| Where | What | Format |
|---|---|---|
| `storage.json` | `telemetry.machineId`, `macMachineId` | 64-char sha256 hex |
| | `telemetry.sqmId` | `{GUID}` |
| | `telemetry.devDeviceId` | UUID |
| `state.vscdb` (sqlite) | the same 5 keys | — |
| `out/main.js` | the machineId **generation function** | patched |

The `main.js` patch (the part that breaks in other tools) is done
**4 ways at once**, each matched by *structure*, not exact names:

1. The `sha256(mac-address).digest("hex")` function → return fresh ID
2. The MAC-address getter (`Unable to retrieve mac address` fallback)
3. The Windows registry sqmId lookup
4. The `vscode/deviceid` getter

Every replacement carries `/*v1*/`…`/*v4*/` sentinels — re-running
detects previous patches and re-patches cleanly after Cursor updates.
Generated IDs **exactly match Cursor's expected formats** (the 64-hex
detail is where most other tools quietly fail). Minified identifiers
like `$8t` are matched with `$`-aware patterns — the #1 killer of
naive scripts.

**Why `extend` is honest:** raising the client cap (`Cni=2e5` → `9e6`)
removes the *UI* block. The **server** still enforces final limits —
this makes Cursor keep working until the server says stop, not forever.
Combined with ID rotation it stretches a trial meaningfully; alone it
just delays the error message.

## ⚠️ Honest limits

- If Cursor flags your **account** (not device), no local tool helps —
  a fresh account is the reliable path. That's Cursor's server-side design.
- The usage API rejected our local-token auth on Cursor 3.30.14 — the
  exact-numbers path is the browser-cookie paste (2 minutes, one time).
- ToS: this evades usage limits — use for genuine trial evaluation on
  your own machine, not account farms. You accept the risk.

## 🛡️ Safety

- **Everything backed up** before any change
  (`globalStorage/cursor-reset-backups/`)
- **`restore`** undoes main.js in one command
- **Login data is never touched or auto-restored**
- `verify` is CI-tested; ID formats asserted on every push
- Development never touched a real Cursor install — all patching was
  simulated on copies and validated with `node --check`

## ❓ FAQ

**Does it work after Cursor updates?**
That's the whole design. Structural patterns + `$`-aware matching +
sentinel re-patching + the storage/vscdb layer keep working when
exact-match scripts break. If a strategy misses, `verify` tells you which.

**"Too many free trial accounts used on this machine" vs "trial request
limit" — same fix?**
Yes — both key on the device identifiers this tool rotates.

**Can it make my trial infinite?**
No honest tool can: the server enforces final limits. What this does is
rotate the *device* identity (unlimited resets) and stretch the *session*
limits (client cap + watching). That's the honest maximum.

**Is this the same as cursor-free-vip / ai-auto-free?**
Same core idea, rebuilt clean-room (neither repo's code is MIT).
What's different: formats-correct ID generation, 4-strategy patching
that survives updates, usage checker, honest docs, MIT license, no
self-promo buttons inside Cursor.

## 🏗️ Build the desktop app yourself

```bash
# macOS (.dmg):
./build_mac.sh        # → dist/cursor-reset.dmg

# Windows (.exe):
powershell -File build_windows.ps1   # → dist\cursor-reset.exe
```

## 🧰 The toolkit

| Stage | Tool | What it covers |
|---|---|---|
| Design | [nativetap](https://github.com/awaisdev5765/nativetap) | Mobile UI rules for AI agents |
| Code | [prism_doctor](https://pub.dev/packages/prism_doctor) | Code audit |
| Claims | [factcheck](https://github.com/awaisdev5765/factcheck) | AI-written content CI gate |
| **Trial** | **cursor-reset** (this repo) | **Device identity + limits** |
| Launch | [shipcheck](https://pub.dev/packages/shipcheck) | Store readiness |

## License

MIT — see [LICENSE](LICENSE).
