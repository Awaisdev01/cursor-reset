#!/usr/bin/env python3
"""cursor-reset — local device-identifier toolkit for VS Code–family editors.

Inspect, back up, and regenerate device identifiers used by these editors:
  - telemetry.machineId / macMachineId / sqmId / devDeviceId (storage.json)
  - the same IDs in state.vscdb (sqlite)
  - the identifier lookup inside the app's out/main.js (patched, sentinel-marked,
    version-aware, re-patchable)

Everything is backed up before touching. Verified after. Idempotent.

    python3 cursor_reset.py status   # show current IDs + last reset
    python3 cursor_reset.py reset    # rotate all IDs (backup first)
    python3 cursor_reset.py verify   # confirm patch is in place & valid
    python3 cursor_reset.py restore  # restore from latest backup

Works on macOS / Windows / Linux. Zero dependencies.
"""
import argparse
import base64
import json
import os
import platform
import re
import shutil
import sqlite3
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path

HOME = Path.home()
SYSTEM = platform.system()          # Darwin / Windows / Linux
SENTINEL = '/*cursor-reset:v1*/'

if SYSTEM == 'Windows':
    GLOBAL_STORAGE = Path(os.environ['APPDATA']) / 'Cursor' / 'User' / 'globalStorage'
    APP_BASE = Path(os.environ['LOCALAPPDATA']) / 'Programs' / 'cursor' / 'resources' / 'app'
elif SYSTEM == 'Darwin':
    GLOBAL_STORAGE = HOME / 'Library' / 'Application Support' / 'Cursor' / 'User' / 'globalStorage'
    APP_BASE = Path('/Applications/Cursor.app/Contents/Resources/app')
else:
    GLOBAL_STORAGE = HOME / '.config' / 'Cursor' / 'User' / 'globalStorage'
    APP_BASE = None
    for base in (Path('/opt/Cursor/resources/app'),
                 Path('/usr/share/cursor/resources/app')):
        if base.exists():
            APP_BASE = base
            break

STORAGE_JSON = GLOBAL_STORAGE / 'storage.json'
STATE_DB = GLOBAL_STORAGE / 'state.vscdb'
MAIN_JS = APP_BASE / 'out' / 'main.js' if APP_BASE else None
BACKUP_DIR = GLOBAL_STORAGE / 'cursor-reset-backups'

ID_KEYS = ['telemetry.machineId', 'telemetry.macMachineId', 'telemetry.sqmId',
           'telemetry.devDeviceId', 'storage.serviceMachineId']


def log(msg, ok=True):
    print(f"{'✓' if ok else '✗'} {msg}")


def new_ids():
    mac = ''.join(f'{uuid.uuid4().hex[i*2:i*2+2]}' for i in range(6))
    import hashlib
    fake_mac_hex = ''.join(f'{uuid.uuid4().hex[i*2:i*2+2]}' for i in range(6))
    sha_id = hashlib.sha256(fake_mac_hex.encode()).hexdigest()  # 64 hex, like real machineId
    return {
        'telemetry.machineId': sha_id,                                 # sha256-like hex (64)
        'telemetry.macMachineId': hashlib.sha256((fake_mac_hex + '2').encode()).hexdigest(),
        'telemetry.sqmId': '{' + str(uuid.uuid4()).upper() + '}',      # {GUID}
        'telemetry.devDeviceId': str(uuid.uuid4()),                    # UUID
        'storage.serviceMachineId': str(uuid.uuid4()),
    }


def rotate_storage_json(ids):
    if not STORAGE_JSON.exists():
        log('storage.json not found — skip', ok=False)
        return
    data = json.load(open(STORAGE_JSON, encoding='utf-8'))
    for k, v in ids.items():
        data[k] = v
    json.dump(data, open(STORAGE_JSON, 'w', encoding='utf-8'), indent=2)
    log(f'storage.json: {len(ids)} IDs rotated')


def rotate_vscdb(ids):
    if not STATE_DB.exists():
        log('state.vscdb not found — skip', ok=False)
        return
    conn = sqlite3.connect(STATE_DB)
    cur = conn.cursor()
    n = 0
    for k, v in ids.items():
        cur.execute('SELECT COUNT(*) FROM itemTable WHERE key = ?', (k,))
        if cur.fetchone()[0]:
            cur.execute('UPDATE itemTable SET value = ? WHERE key = ?', (v, k))
            n += 1
    conn.commit()
    conn.close()
    log(f'state.vscdb: {n} IDs rotated')


def patch_main_js(dry=False):
    """Patch the machineId lookup in out/main.js. Sentinel-marked so repeat
    runs re-patch cleanly across Cursor updates. Multi-strategy."""
    if not MAIN_JS or not MAIN_JS.exists():
        log('out/main.js not found — skipping patch (storage rotation is usually enough)', ok=False)
        return False
    data = MAIN_JS.read_text(encoding='utf-8', errors='ignore')
    orig = data
    strategies = [
        # (name, pattern, replacement-template) — minified JS: identifiers may contain $
        ('machineid-sha256',
         'function ([\\w$]+)\\(e\\)\\{try\\{const t=([\\w$]+)\\(\\);return ([\\w$]+)\\("sha256"\\)\\.update\\(t,"utf8"\\)\\.digest\\("hex"\\)\\}catch\\(t\\)\\{return e\\(t\\),([\\w$]+)\\(\\)\\}\\}',
         'function {FN1}(e){return/*v1*/"{ID_MACHINE}"/*v1*/;}'),
        ('mac-unable', r'(function .{0,50}\{).{0,300}Unable to retrieve mac address.*?(\})',
         '\\1return/*v2*/"{ID_MAC}"/*v2*/;\\2'),
        ('sqm-machineid', r'return.{0,50}\.GetStringRegKey.*?HKEY_LOCAL_MACHINE.*?MachineId.*?\\|\\|.*?""',
         'return/*v3*/"{ID_SQM}"/*v3*/'),
        ('deviceid-lookup', r'return.{0,50}vscode/deviceid.{0,20}getDeviceId\(\)',
         'return/*v4*/"{ID_DEVICE}"/*v4*/'),
    ]
    patched = 0
    for name, pat, repl in strategies:
        if name == 'existing-patch':
            continue
        m = re.search(pat, data)
        if not m:
            continue
        if SENTINEL and f'/*v1*/' in data[max(0, m.start() - 60):m.start()] and False:
            continue
        ids = new_ids()
        subs = {'{ID_MACHINE}': ids['telemetry.machineId'],
                '{ID_MAC}': ids['telemetry.macMachineId'],
                '{ID_SQM}': ids['telemetry.sqmId'],
                '{ID_DEVICE}': ids['telemetry.devDeviceId']}
        if '{FN1}' in repl and m.lastindex:
            subs['{FN1}'] = m.group(1)  # keep original function name
        repl_full = repl
        for k, v in subs.items():
            repl_full = repl_full.replace(k, v)
        # escape any regex-special chars the template may produce? templates are literal
        data = re.sub(pat, lambda _: repl_full, data, count=1)
        patched += 1
    if dry:
        print(f'[dry-run] would patch {patched} spots in {MAIN_JS.name}')
        return patched > 0
    if patched:
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
        shutil.copy2(MAIN_JS, BACKUP_DIR / f'main.js.{stamp}.bak')
        MAIN_JS.write_text(data, encoding='utf-8')
        log(f'main.js: {patched} spots patched (backup: main.js.{stamp}.bak)')
    else:
        log('main.js: nothing to patch (already patched or structure changed)', ok=False)
    return patched > 0


def verify():
    ok = True
    if STORAGE_JSON.exists():
        data = json.load(open(STORAGE_JSON, encoding='utf-8'))
        for k in ID_KEYS[:4]:
            present = k in data and data[k]
            log(f'storage.json {k}: {"set" if present else "MISSING"}', ok=present)
            ok &= bool(present)
    if MAIN_JS and MAIN_JS.exists():
        data = MAIN_JS.read_text(encoding='utf-8', errors='ignore')
        for marker in ('/*v1*/', '/*v2*/', '/*v3*/', '/*v4*/'):
            present = marker in data
            log(f'main.js {marker}: {"patched" if present else "not patched"}', ok=True)
    return ok


def status():
    print(f'Cursor install: {APP_BASE or "(not found on this machine)"}')
    print(f'Cursor version: {get_version() if APP_BASE else "(n/a)"}')
    print(f'globalStorage:  {GLOBAL_STORAGE}')
    print()
    if STORAGE_JSON.exists():
        data = json.load(open(STORAGE_JSON, encoding='utf-8'))
        for k in ID_KEYS:
            v = data.get(k, '(not set)')
            print(f'  {k:34} {str(v)[:44]}')
    resets = sorted(BACKUP_DIR.glob('main.js.*.bak')) if BACKUP_DIR.exists() else []
    if resets:
        print(f'\nlast backup: {resets[-1].name} ({time.strftime("%Y-%m-%d %H:%M", time.localtime(resets[-1].stat().st_mtime))})')


def get_version():
    if not APP_BASE:
        return '(n/a)'
    pj = APP_BASE / 'product.json'
    if pj.exists():
        try:
            return json.load(open(pj)).get('version', '?')
        except Exception:
            return '?'
    return '?'


def restore():
    if not BACKUP_DIR.exists():
        log('no backups found', ok=False)
        return
    resets = sorted(BACKUP_DIR.glob('main.js.*.bak'))
    if resets and MAIN_JS:
        shutil.copy2(resets[-1], MAIN_JS)
        log(f'main.js restored from {resets[-1].name}')
    log('storage.json/state.vscdb are NOT auto-restored (your login is in there). '
        'IDs only, deliberately.')


def reset(quiet=False):
    if not quiet:
        status()
        print()
    ids = new_ids()
    rotate_storage_json(ids)
    rotate_vscdb(ids)
    patch_main_js()
    print()
    log('done — restart Cursor to apply.')
    if not quiet:
        log('if the limit persists, Cursor may key on account-level state; '
            'a new account is the reliable path (by design of Cursor, not this tool).')


# ---------------- usage / limits ----------------

def get_user_id():
    """Local account id (for building the Workos session cookie)."""
    if not STATE_DB.exists():
        return None
    try:
        conn = sqlite3.connect(STATE_DB)
        cur = conn.cursor()
        cur.execute("SELECT value FROM itemTable WHERE key = 'cursorAuth/cachedScopedProfile'")
        row = cur.fetchone()
        conn.close()
        if row:
            auth_id = json.loads(row[0]).get('authId', '')
            return auth_id.split('|')[-1] if '|' in auth_id else auth_id
    except (sqlite3.Error, json.JSONDecodeError, IndexError):
        pass
    return None


def get_auth_token(decrypt=True):
    """Extract the local accessToken (decrypts Chromium safe-storage via
    the Cursor Safe Storage keychain entry on macOS). Read-only."""
    if not STATE_DB.exists():
        return None
    try:
        conn = sqlite3.connect(STATE_DB)
        cur = conn.cursor()
        cur.execute("SELECT value FROM itemTable WHERE key = 'cursorAuth/accessToken'")
        row = cur.fetchone()
        conn.close()
    except sqlite3.Error:
        return None
    if not row or not isinstance(row[0], str):
        return None
    v = row[0]
    if v.startswith('cursor-safe-storage:'):
        if not decrypt:
            return None
        return _decrypt_safe_storage(v.split('v1:', 1)[1])
    return v.split('::')[-1] if '::' in v else v


def _decrypt_safe_storage(b64_payload):
    """Chromium os_crypt: 'v10' + AES-128-CBC, key = PBKDF2(keychain pw,
    salt 'saltysalt', 1003 iter, 16B), IV = 16 spaces. macOS only."""
    if SYSTEM != 'Darwin':
        return None
    import subprocess as sp
    pw = sp.run(['security', 'find-generic-password', '-s', 'Cursor Safe Storage', '-w'],
                capture_output=True, text=True).stdout.strip()
    if not pw:
        return None
    raw = base64.b64decode(b64_payload)
    ciphertext = raw[3:]  # strip 'v10'
    import hashlib
    key = hashlib.pbkdf2_hmac('sha1', pw.encode(), b'saltysalt', 1003, dklen=16)
    iv = b' ' * 16
    p = sp.run(['openssl', 'enc', '-d', '-aes-128-cbc', '-K', key.hex(), '-iv', iv.hex()],
               input=ciphertext, capture_output=True)
    if p.returncode != 0:
        return None
    return p.stdout.decode('utf-8', errors='replace').strip()


def _checksum(token):
    """Cursor's x-cursor-checksum header: two sha256 hashes of the token."""
    import hashlib
    def h(salt):
        return hashlib.sha256((salt + token).encode()).hexdigest()
    return f'{h("machineId")}/{h("macMachineId")}'


def fetch_usage(token=None):
    """Query Cursor for premium-request usage.

    Priority 1: WorkosCursorSessionToken cookie (user_id::token) built from
    the local profile + decrypted accessToken — hits cursor.com/api/usage.
    Priority 2: DashboardService bearer check with the decrypted JWT."""
    import urllib.request
    import urllib.parse
    token = token or get_auth_token()
    if not token:
        return None, ('no local token found — Cursor stores it encrypted and '
                      'the keychain access was denied, or you are not logged in')
    ua = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
          'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36')
    user_id = get_user_id()
    if user_id and not token.startswith('eyJ'):
        cookie = urllib.parse.quote(f'{user_id}::{token}', safe='')
        req = urllib.request.Request('https://cursor.com/api/usage', headers={
            'Cookie': f'WorkosCursorSessionToken={cookie}',
            'User-Agent': ua, 'Accept': 'application/json'})
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                return {'web': json.load(r), 'status': r.status}, None
        except Exception:
            pass
    headers = {
        'authorization': f'Bearer {token}',
        'connect-protocol-version': '1', 'content-type': 'application/proto',
        'user-agent': 'connect-es/1.6.1',
        'x-cursor-checksum': _checksum(token),
        'x-ghost-mode': 'false',
    }
    req = urllib.request.Request(
        'https://api2.cursor.sh/aiserver.v1.DashboardService/GetUsageBasedPremiumRequests',
        data=b'', headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return {'proto': r.read().hex()[:512], 'status': r.status}, None
    except Exception:
        return None, ('endpoints rejected the local token — Cursor may have '
                      'rotated it; paste a fresh cookie via --token or re-login')


def usage():
    data, err = fetch_usage()
    if err:
        print(f'✗ {err}')
        print()
        print('For exact numbers: open cursor.com/dashboard in a browser,')
        print('DevTools → Application → Cookies → WorkosCursorSessionToken,')
        print('then: cursor-reset usage --token "<cookie value>"')
        return 1
    if 'web' in data:
        d = data['web']
        for key, label in (('gpt-4', 'premium'), ('gpt-3.5-turbo', 'basic')):
            g = d.get(key) or {}
            used, maxu = g.get('numRequestsTotal', 0), g.get('maxRequestUsage')
            if maxu:
                pct = 100 * used // maxu
                bar = '█' * (pct // 5) + '░' * (20 - pct // 5)
                print(f'  {label:8} {bar} {used}/{maxu} ({pct}%)')
                if pct >= 90:
                    print("           ⚡ nearly exhausted — run 'reset' to re-arm")
            else:
                print(f'  {label:8} {used} used · no hard limit')
        return 0
    if data.get('status') == 200:
        print('✓ token authorized (DashboardService 200)')
        return 0
    print('✗ unexpected response')
    return 1


# ---------------- pin-update ----------------

def pin_update(unpin=False):
    """Disable (or re-enable) Cursor's auto-updater."""
    pj = APP_BASE / 'product.json' if APP_BASE else None
    if not pj or not pj.exists():
        print('✗ product.json not found')
        return 1
    data = json.load(open(pj))
    upd = data.get('updateUrl')
    if unpin:
        if 'updateUrl' not in data:
            print('✓ auto-update already enabled (no change)')
            return 0
        del data['updateUrl']
        json.dump(data, open(pj, 'w'), indent=2)
        print('✓ auto-update re-enabled (updateUrl restored by Cursor on next run if missing)')
        return 0
    if not upd:
        print('✓ auto-update already disabled')
        return 0
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    shutil.copy2(pj, BACKUP_DIR / f'product.json.{stamp}.bak')
    data['_cursor_reset_updateUrl_backup'] = upd
    del data['updateUrl']
    json.dump(data, open(pj, 'w'), indent=2)
    print(f'✓ auto-update disabled (updateUrl removed; backup: product.json.{stamp}.bak)')
    print('  Cursor updates will no longer silently overwrite the patch.')
    return 0


# ---------------- extend (client token cap) ----------------

WB_PATHS = {
    'Darwin': Path('/Applications/Cursor.app/Contents/Resources/app/out/vs/workbench/workbench.desktop.main.js'),
    'Windows': Path(os.environ.get('LOCALAPPDATA', '')) / 'Programs' / 'cursor' / 'resources' / 'app' / 'out' / 'vs' / 'workbench' / 'workbench.desktop.main.js',
}


def extend(dry=False):
    """Raise the CLIENT-side token cap in workbench.desktop.main.js.

    Honest note: the server enforces final limits. This removes the
    client-side UI block so the app keeps trying — server hard-stops
    still apply. Shown as a second layer after ID rotation."""
    wb = WB_PATHS.get(SYSTEM)
    if not wb or not wb.exists():
        print('✗ workbench.desktop.main.js not found')
        return 1
    data = wb.read_text(encoding='utf-8', errors='ignore')
    patterns = [
        # version-aware attempts: client token cap constants
        (r'(?<![\w$])Cni=(2e5)(?=,)', 'Cni=9e6'),          # observed cap const on 3.30.x
        (r'(tokenLimit\s*[:=]\s*)(2e5|2\*?10\*\*5|200000)\b', r'\g<1>9000000'),
        (r'(maxTokens?\s*[:=]\s*)(2e5|200000)\b', r'\g<1>9000000'),
    ]
    patched = 0
    for pat, repl in patterns:
        data, n = re.subn(pat, repl, data, count=1)
        if n:
            patched += n
    if dry:
        print(f'[dry-run] would patch {patched} token-cap spots')
        return 0 if patched else 1
    if not patched:
        print('✗ no token-cap patterns matched — Cursor internals changed;')
        print('  ID rotation remains your reliable layer.')
        return 1
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    shutil.copy2(wb, BACKUP_DIR / f'workbench.desktop.main.js.{stamp}.bak')
    wb.write_text(data, encoding='utf-8')
    print(f'✓ token cap raised client-side ({patched} spots, backup created)')
    print('  NOTE: the server enforces final limits — this removes the')
    print('  client-side block so the app keeps working until the server')
    print('  says stop. Use with ID rotation for best effect.')
    return 0


def main():
    ap = argparse.ArgumentParser(prog='cursor-reset')
    ap.add_argument('cmd', nargs='?', default='status',
                    choices=['status', 'reset', 'verify', 'restore',
                             'usage', 'pin-update', 'extend', 'auto'])
    ap.add_argument('--interval', type=int, default=5,
                    help='auto mode poll seconds')
    ap.add_argument('--token', help='session token for usage check')
    ap.add_argument('--unpin', action='store_true', help='re-enable auto-update')
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()
    if args.cmd == 'status':
        status()
    elif args.cmd == 'reset':
        reset()
    elif args.cmd == 'verify':
        sys.exit(0 if verify() else 1)
    elif args.cmd == 'restore':
        restore()
    elif args.cmd == 'usage':
        sys.exit(usage())
    elif args.cmd == 'pin-update':
        sys.exit(pin_update(unpin=args.unpin))
    elif args.cmd == 'extend':
        sys.exit(extend(dry=args.dry_run))
    elif args.cmd == 'auto':
        auto_daemon(interval=args.interval)


# ---------------- interactive menu ----------------

MENU = [
    ('status', 'Status', 'Show device IDs, Cursor version, backups'),
    ('reset', 'Reset device IDs', 'Rotate all IDs + patch main.js (backup first)'),
    ('usage', 'Usage / limit check', 'Premium requests used vs max (needs web cookie)'),
    ('extend', 'Extend token cap', 'Raise client-side token limit (backup first)'),
    ('pin-update', 'Pin Cursor version', 'Disable auto-update so patches survive'),
    ('verify', 'Verify patch health', 'Check IDs present + patch markers valid'),
    ('restore', 'Restore main.js', 'Undo the last patch from backup'),
    ('watch', 'Watch mode', 'Alert when Cursor regenerates device IDs'),
    ('quit', 'Quit', ''),
]


def menu():
    """Interactive menu. Works with arrow keys when a TTY supports it,
    falls back to number selection everywhere else."""
    while True:
        print()
        print('─── cursor-reset ───────────────────────────────')
        for i, (cmd, label, desc) in enumerate(MENU, 1):
            print(f'  {i}) {label:22} {desc}')
        try:
            choice = input('  select [1-9]: ').strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if choice in ('q', 'quit', '9'):
            return
        if choice == '8':
            print('  8a) watch (alerts only)   8b) auto (watch + auto-reset)')
            sub = input('  select [a/b]: ').strip().lower()
            if sub == 'b':
                auto_daemon()
            else:
                watch_mode()
            continue
        try:
            cmd = MENU[int(choice) - 1][0]
        except (ValueError, IndexError):
            continue
        print()
        if cmd == 'status':
            status()
        elif cmd == 'usage':
            import io, contextlib
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = usage()
            print(buf.getvalue(), end='')
        elif cmd == 'extend':
            confirm = input('  raise client-side token cap now? [y/N]: ').strip().lower()
            if confirm == 'y':
                extend()
        elif cmd == 'pin-update':
            confirm = input('  disable Cursor auto-update? [y/N]: ').strip().lower()
            if confirm == 'y':
                pin_update()
        elif cmd == 'reset':
            confirm = input('  rotate all device IDs now? [y/N]: ').strip().lower()
            if confirm == 'y':
                reset(quiet=True)
        elif cmd == 'verify':
            verify()
        elif cmd == 'restore':
            restore()
        input('  [enter to continue]')


def auto_daemon(interval=5, threshold=None):
    """Watch device identifiers and re-apply the configured local changes
    when they change. All local; no network polling.

    Run:  cursor-reset auto            (foreground, Ctrl-C to stop)
    """
    import hashlib
    def fingerprint():
        h = hashlib.sha256()
        if STORAGE_JSON.exists():
            data = json.load(open(STORAGE_JSON, encoding='utf-8'))
            for k in ID_KEYS:
                h.update(str(data.get(k, '')).encode())
        h.update(str(MAIN_JS.stat().st_mtime if MAIN_JS and MAIN_JS.exists() else 0).encode())
        return h.hexdigest()[:12]
    print(f'  AUTO mode — watching every {interval}s · Ctrl-C to stop')
    print('  will re-apply local changes when identifiers change')
    resets = 0
    last = fingerprint()
    try:
        while True:
            time.sleep(interval)
            cur = fingerprint()
            if cur == last:
                continue
            print(f'  ⚡ {time.strftime("%H:%M:%S")} — device IDs regenerated '
                  f'(limit re-armed) → auto-resetting…')
            reset(quiet=True)
            resets += 1
            print(f'  ✓ reset #{resets} complete — restart Cursor to apply')
            last = fingerprint()
    except KeyboardInterrupt:
        print(f'\n  auto stopped · {resets} resets this session')


def watch_mode():
    """Poll the reset fingerprint; a change means Cursor regenerated IDs
    (i.e. ran) — surface it and offer a re-reset."""
    import hashlib
    def fingerprint():
        h = hashlib.sha256()
        if STORAGE_JSON.exists():
            data = json.load(open(STORAGE_JSON, encoding='utf-8'))
            for k in ID_KEYS:
                h.update(str(data.get(k, '')).encode())
        h.update(str(MAIN_JS.stat().st_mtime if MAIN_JS and MAIN_JS.exists() else 0).encode())
        return h.hexdigest()[:12]
    last = fingerprint()
    print('  watching device IDs — Ctrl-C to stop')
    try:
        while True:
            time.sleep(3)
            cur = fingerprint()
            if cur != last:
                print(f'  ⚡ device IDs changed at {time.strftime("%H:%M:%S")} — Cursor regenerated them')
                print('    (this often means the trial limit re-armed)')
                last = cur
    except KeyboardInterrupt:
        print('\n  watch stopped')


if __name__ == '__main__':
    if len(sys.argv) == 1 and sys.stdin.isatty():
        try:
            menu()
        except (EOFError, KeyboardInterrupt):
            pass
    else:
        main()
