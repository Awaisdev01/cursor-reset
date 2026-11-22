#!/usr/bin/env python3
"""cursor-reset GUI — native desktop app wrapping the reset engine.

Built with tkinter (stdlib): ships as a .dmg (macOS, via py2app) and .exe
(Windows, via PyInstaller). No web view, no dependencies.
"""
import json
import os
import sys
import threading
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox

# when frozen (py2app/PyInstaller), import the engine from the bundle
HERE = os.path.dirname(os.path.abspath(sys.executable if getattr(sys, 'frozen', False) else __file__))
sys.path.insert(0, HERE)

import cursor_reset as engine  # noqa: E402


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('cursor-reset')
        self.geometry('760x560')
        self.minsize(680, 480)
        self._build()
        self.after(200, self.refresh_status)

    # ---------- UI ----------
    def _build(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        top = ttk.Frame(self, padding=14)
        top.grid(row=0, column=0, sticky='ew')
        ttk.Label(top, text='cursor-reset', font=('SF Pro Display', 20, 'bold')
                  if sys.platform == 'Darwin' else ('Segoe UI', 18, 'bold')
                  ).pack(side='left')
        ver = engine.get_version() if engine.APP_BASE else '(Cursor not found)'
        ttk.Label(top, text=f'Cursor {ver}', foreground='#64748b').pack(side='left', padx=10)
        self.state_lbl = ttk.Label(top, text='checking…', foreground='#f59e0b')
        self.state_lbl.pack(side='right')

        btns = ttk.Frame(self, padding=(14, 4))
        btns.grid(row=1, column=0, sticky='ew')
        for label, cmd in (('Reset device IDs', self.do_reset),
                           ('Verify', self.do_verify),
                           ('Restore main.js', self.do_restore),
                           ('Refresh', self.refresh_status)):
            ttk.Button(btns, text=label, command=cmd).pack(side='left', padx=4)

        self.note = ttk.Notebook(self)
        self.note.grid(row=2, column=0, sticky='nsew', padx=14, pady=10)

        # tab 1: IDs
        idf = ttk.Frame(self.note, padding=10)
        self.id_tree = ttk.Treeview(idf, columns=('key', 'value'), show='headings')
        self.id_tree.heading('key', text='ID')
        self.id_tree.heading('value', text='value')
        self.id_tree.column('key', width=240)
        self.id_tree.column('value', width=420)
        self.id_tree.pack(fill='both', expand=True)
        self.note.add(idf, text='Device IDs')

        # tab 2: log
        lf = ttk.Frame(self.note, padding=6)
        self.log = scrolledtext.ScrolledText(lf, font=('Menlo', 11) if sys.platform == 'Darwin'
                                             else ('Consolas', 10), state='disabled',
                                             background='#0a0e1a', foreground='#22c55e')
        self.log.pack(fill='both', expand=True)
        self.note.add(lf, text='Activity')

    # ---------- actions ----------
    def _log(self, msg):
        self.log.configure(state='normal')
        self.log.insert('end', msg + '\n')
        self.log.see('end')
        self.log.configure(state='disabled')

    def refresh_status(self):
        for i in self.id_tree.get_children():
            self.id_tree.delete(i)
        if engine.STORAGE_JSON.exists():
            data = json.load(open(engine.STORAGE_JSON, encoding='utf-8'))
            for k in engine.ID_KEYS:
                self.id_tree.insert('', 'end', values=(k, str(data.get(k, '(not set)'))))
        patched = False
        if engine.MAIN_JS and engine.MAIN_JS.exists():
            data = engine.MAIN_JS.read_text(encoding='utf-8', errors='ignore')
            patched = '/*v1*/' in data
        if patched:
            self.state_lbl.configure(text='● patched', foreground='#22c55e')
        else:
            self.state_lbl.configure(text='● not patched', foreground='#ef4444')

    def _worker(self, fn):
        threading.Thread(target=fn, daemon=True).start()

    def do_reset(self):
        if not messagebox.askyesno('cursor-reset',
                                   'Rotate all device IDs now?\n\nA backup of main.js is created first. Restart Cursor after.'):
            return
        self._log('$ reset')
        self._worker(self._reset_job)

    def _reset_job(self):
        ids = engine.new_ids()
        self._log(f'✓ new IDs generated (sha256-format machine IDs)')
        self.after(0, lambda: self._run_step('storage.json', engine.rotate_storage_json, ids))
        self.after(0, lambda: self._run_step('state.vscdb', engine.rotate_vscdb, ids))
        try:
            engine.patch_main_js()
            self._log('✓ main.js patched (backup created)')
        except Exception as e:
            self._log(f'✗ main.js patch: {e}')
        self._log('✓ done — restart Cursor to apply.')
        self.after(0, self.refresh_status)

    def _run_step(self, name, fn, arg):
        try:
            fn(arg)
            self._log(f'✓ {name} rotated')
        except Exception as e:
            self._log(f'✗ {name}: {e}')

    def do_verify(self):
        self._log('$ verify')
        import io, contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            ok = engine.verify()
        self._log(buf.getvalue().strip())
        self._log('✓ healthy' if ok else '✗ issues found')
        self.refresh_status()

    def do_restore(self):
        if not messagebox.askyesno('cursor-reset', 'Restore main.js from the latest backup?'):
            return
        engine.restore()
        self._log('✓ main.js restored')
        self.refresh_status()


if __name__ == '__main__':
    App().mainloop()
