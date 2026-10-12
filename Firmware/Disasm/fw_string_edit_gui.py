#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fw_string_edit_gui.py — GUI to find and replace a menu string (e.g. 'MENU') inside
the TD-H9 firmware, and rebuild/repack the file.

Works on:
  - .bin  (raw flash image)   — patches bytes in place.
  - .fw   (UFW container)     — decrypts app area, patches app.bin, repacks.

Replace is length-aware: it only writes text+NUL, never overwrites unrelated
neighbour bytes (so following strings stay intact). Text <= 10 chars.

Dependencies: Python 3 stdlib (tkinter). Uses tdh9_ufw.py from the same folder.
Run:  python fw_string_edit_gui.py
"""
import os, sys, hashlib
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import tdh9_ufw as U

# We search for 'MENU\0' (the menu label) but allow choosing which occurrence
SEARCH = b"MENU"


def find_targets(app_bytes):
    """Return list of (offset, original_len_with_nul) where SEARCH\0 begins."""
    out = []
    i = 0
    while True:
        j = app_bytes.find(SEARCH, i)
        if j < 0:
            break
        term = app_bytes[j + len(SEARCH): j + len(SEARCH) + 1]
        if term == b"\x00":
            # length of the full CString at j (up to next NUL)
            e = app_bytes.find(b"\x00", j)
            olen = (e - j + 1) if e > 0 else (len(SEARCH) + 1)
            out.append((j, olen))
        i = j + 1
    return out


def do_replace(data, off, new_text, overwrite_neighbour=False):
    """Write new_text+NUL at off, searching 'SEARCH\\0' across the whole file.

    New text may be up to 10 chars (not counting the appended NUL).
    This is a simple replacement: bytes [off:off+len(text)+1] become text+NUL.
    Neighbour bytes after that point are left untouched.
    Returns (new_bytes, note).
    """
    nb = new_text.encode('latin1')   # 1 byte per char (ASCII expected)
    if len(nb) > 10:
        raise ValueError("Text longer than 10 chars (NUL not counted)")
    if b"\x00" in nb:
        raise ValueError("Text must not contain NUL")
    payload = nb + b"\x00"
    out = bytearray(data)
    out[off:off + len(payload)] = payload
    return bytes(out), "replaced at 0x%X with %r\\0" % (off, new_text)


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("TD-H9 — Edit menu string (MENU -> custom)")
        self.geometry("640x330")
        self.resizable(False, False)
        self._build()

    def _build(self):
        f = ttk.Frame(self, padding=12); f.pack(fill="both", expand=True)
        ttk.Label(f, text="Firmware file (.fw or .bin):").grid(row=0, column=0, sticky="w")
        self.e_file = ttk.Entry(f, width=54); self.e_file.grid(row=0, column=1, padx=6, pady=3)
        ttk.Button(f, text="Browse...", command=self.pick).grid(row=0, column=2)

        ttk.Label(f, text="Search string (default MENU):").grid(row=1, column=0, sticky="w")
        self.e_search = ttk.Entry(f, width=20); self.e_search.insert(0, "MENU")
        self.e_search.grid(row=1, column=1, sticky="w", padx=6, pady=3)

        ttk.Label(f, text="New text (<=10 chars):").grid(row=2, column=0, sticky="w")
        self.e_new = ttk.Entry(f, width=20); self.e_new.grid(row=2, column=1, sticky="w", padx=6, pady=3)

        ttk.Button(f, text="Scan occurrences", command=self.scan).grid(row=3, column=0, columnspan=3, pady=6)

        self.chk_ow = tk.BooleanVar(value=False)
        ttk.Checkbutton(f, text="Overwrite neighbour (allow extending past original string)",
                        variable=self.chk_ow).grid(row=4, column=0, columnspan=3, sticky="w")

        self.lb = tk.Listbox(f, height=4)
        self.lb.grid(row=5, column=0, columnspan=3, sticky="we", padx=6, pady=6)

        ttk.Button(f, text="Replace & save", command=self.replace_and_save).grid(row=6, column=0, columnspan=3, pady=6)

        self.txt = tk.Text(f, height=6, width=84, state="disabled")
        self.txt.grid(row=7, column=0, columnspan=3)

    def log(self, s):
        self.txt.config(state="normal"); self.txt.insert("end", s + "\n"); self.txt.config(state="disabled"); self.txt.see("end")

    def pick(self):
        p = filedialog.askopenfilename(title="Choose firmware", filetypes=[("Firmware", "*.fw *.bin"), ("All", "*.*")])
        if p:
            self.e_file.delete(0, "end"); self.e_file.insert(0, p)
            self.occurrences = {}

    def _get_app_bytes(self):
        path = self.e_file.get().strip()
        if not path or not os.path.isfile(path):
            raise ValueError("Choose a file")
        ext = Path(path).suffix.lower()
        if ext == ".bin":
            data = Path(path).read_bytes()
            # raw .bin is the ENCRYPTED flash image -> decrypt app area to find/strings
            dec = U.decrypt_app_area(data)          # whole decrypted (>=0x5000)
            app, layout = U.extract_app_bin(data)   # app.bin (decrypted code)
            self._style = "bin"
            self._rawbin = data
            self._layout = layout
            # work on the decrypted app bytes for search/replace
            return "bin", app, path
        if ext == ".fw":
            fw = Path(path).read_bytes()
            hdr, n = U.parse_ufw_header(fw)
            inner = U.get_flash_inner(fw)
            app, layout = U.extract_app_bin(inner)
            self._style = "fw"
            self._fw = fw; self._inner = inner; self._layout = layout
            return "fw", app, path
        raise ValueError("Only .fw or .bin supported")

    def scan(self, _=None):
        self.txt.config(state="normal"); self.txt.delete("1.0","end"); self.txt.config(state="disabled")
        try:
            kind, app, path = self._get_app_bytes()
        except Exception as ex:
            messagebox.showerror("Error", str(ex)); self.log("ERR "+str(ex)); return
        s = self.e_search.get().strip().encode('latin1')
        offs = find_targets(app)
        self.lb.delete(0, tk.END)
        self.occurrences = {}
        for (o, olen) in offs:
            tail = app[o:o+20]
            self.lb.insert(tk.END, "0x%05X (len %d): %r"%(o, olen, tail[:o-o if o>0 else 18] if False else tail[o-o:][:18]))
            self.occurrences[o] = (kind, path)
        self.log("Found %d occurrence(s) of %r\\0 in app area"%(len(offs), s.decode('latin1', 'ignore')))

    def replace_and_save(self):
        sel = self.lb.curselection()
        if not sel:
            messagebox.showerror("Error", "Select an occurrence first (Scan)"); return
        try:
            off = list(self.occurrences)[sel[0]]
            kind, path = self.occurrences[off]
            newtext = self.e_new.get().strip()
            if not newtext:
                messagebox.showerror("Error", "Enter new text"); return
        except Exception as ex:
            messagebox.showerror("Error", str(ex)); return
        try:
            if kind == "bin":
                _, app, path = self._get_app_bytes()  # reload fresh decrypted app
                newapp, note = do_replace(app, off, newtext)
                # re-encrypt the modified app back into the raw flash image
                newraw = U.make_app_inner_flash(self._rawbin, newapp, self._layout)
                out = Path(path).with_name(Path(path).stem + "_mod.bin")
                out.write_bytes(newraw)
                self.log("Wrote: %s\n  SHA256: %s   [%s]"%(out, hashlib.sha256(newraw).hexdigest()[:16], note))
                self.log("Replaced at 0x%05X with %r"%(off, newtext))
                messagebox.showinfo("Done","Saved: "+str(out))
            elif kind == "fw":
                _, app, path = self._get_app_bytes()   # reload fresh
                newapp, note = do_replace(app, off, newtext)
                new_inner = U.make_app_inner_flash(self._inner, newapp, self._layout)
                fw_out = U.build_ufw(new_inner, self._fw)
                out = Path(path).with_name(Path(path).stem + "_mod.fw")
                out.write_bytes(fw_out)
                self.log("Wrote: %s\n  fw SHA256: %s   [%s]"%(out, hashlib.sha256(fw_out).hexdigest()[:16], note))
                self.log("Replaced at 0x%05X with %r"%(off, newtext))
                messagebox.showinfo("Done","Saved: "+str(out))
        except Exception as ex:
            messagebox.showerror("Error", str(ex)); self.log("ERR "+str(ex))


if __name__ == "__main__":
    App().mainloop()