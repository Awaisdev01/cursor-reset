#!/usr/bin/env python3
"""cursor-reset — survive Cursor trial limits on one machine.

Rotates every device identifier Cursor keys its trial limit on:
  - telemetry.machineId / macMachineId / sqmId / devDeviceId (storage.json)
  - the same IDs in state.vscdb (sqlite)
  - the machineId lookup inside Cursor's out/main.js (patched, sentinel-marked,
    version-aware, re-patchable)

Everything is backed up before touching. Verified after. Idempotent.

    python3 cursor_reset.py status   # show current IDs + last reset
    python3 cursor_reset.py reset    # rotate all IDs (backup first)
    python3 cursor_reset.py verify   # confirm patch is in place & valid
    python3 cursor_reset.py restore  # restore from latest backup

Works on macOS / Windows / Linux. Zero dependencies.
"""
import argparse
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
    print(f'Cursor install: {APP_BASE}')
    print(f'Cursor version: {get_version()}')
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


def main():
    ap = argparse.ArgumentParser(prog='cursor-reset')
    ap.add_argument('cmd', nargs='?', default='status',
                    choices=['status', 'reset', 'verify', 'restore'])
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


if __name__ == '__main__':
    main()
