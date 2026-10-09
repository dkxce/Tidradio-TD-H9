#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fw_unpack_gui.py — unpack a TD-H9 firmware image (.fw or .bin) into a .zip.

The .fw file is an UFW container (flashed over USB); the .bin is a raw flash
image (flashed via a CH340/CH341 adapter). Both are handled here.

Layout parameters (APP_SIZE, MD5 offsets, ...) are auto-detected from the
image itself, so different firmware versions are supported. If detection
fails, the v1.0.33 fallback values are used.

Dependencies: Python 3 standard library only (tkinter, zipfile).

Run:  python fw_unpack_gui.py
"""
import os
import sys
import hashlib
import zipfile
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

# Import the shared module from the same folder.
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import tdh9_ufw as U

STOCK_APP_MD5 = "1ed6fe7f07c165e307677972b2853b59"
STOCK_INNER_SHA = "d0df607441a44765127cd5f00e34398f5866712dff3dfb17dc6f1fbf81118dc0"


def unpack_file(path: str, out_zip: str) -> dict:
    """Unpack an .fw or .bin image into out_zip. Returns an info dict."""
    data = Path(path).read_bytes()
    name = Path(path).stem
    ext = Path(path).suffix.lower()
    info = {}

    if ext == ".fw":
        hdr, n = U.parse_ufw_header(data)
        if hdr is None:  # keep signature simple; parser raises on bad input already
            pass
        info["type"] = "UFW"
        inner = U.get_flash_inner(data)
        payload = {}
        for _, e in U.ufw_entries(hdr, n):
            blob = bytes(data[e["eoffset"]: e["eoffset"] + e["esize"]])
            payload[f"ufw_{e['name'] or e['eindex']}.bin"] = blob
    elif ext == ".bin":
        info["type"] = "RAW"
        inner = data
        payload = {"flash.bin": inner}
    else:
        raise ValueError("Only .fw or .bin files are supported")

    # Decrypt the app area and extract app.bin (auto-detected layout).
    dec_full = U.decrypt_app_area(inner)
    app, layout = U.extract_app_bin(inner)
    app_md5 = hashlib.md5(app).hexdigest()

    info["input file"] = name + ext
    info["input size (bytes)"] = len(data)
    info["flash size (bytes)"] = len(inner)
    info["layout note"] = layout.get("note", "?")
    info["detected app_size"] = hex(layout["app_size"])
    info["inner SHA-256"] = hashlib.sha256(inner).hexdigest()
    info["app.bin MD5"] = app_md5
    info["app is STOCK (MD5 matches)"] = (app_md5 == STOCK_APP_MD5)
    info["app version (by string)"] = find_version(app)
    info["app area SHA-256 (decrypted)"] = hashlib.sha256(dec_full).hexdigest()

    # Build the output zip.
    with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("info.txt", render_info(info))
        z.writestr("app.bin", app)
        z.writestr("app_dec_full.bin", dec_full)      # whole decrypted app area
        if ext == ".fw":
            z.writestr("original.fw", data)           # full source .fw as a rebuild template
            hdr, _ = U.parse_ufw_header(data)
            z.writestr("header_ufw.bin", hdr)
        for k, v in payload.items():
            z.writestr(k, v)
    return info


def find_version(app: bytes) -> str:
    """Guess the firmware version substring present in app.bin."""
    for s in (b"V1.0.33", b"V1.0.3", b"V1.0", b"1.0.33"):
        i = app.find(s)
        if i >= 0:
            return app[i:i + len(s)].decode("ascii", "ignore")
    return "?"


def render_info(info: dict) -> str:
    lines = ["=== TD-H9 unpack info ===", ""]
    for k, v in info.items():
        lines.append(f"{k}: {v}")
    return "\n".join(lines) + "\n"


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("TD-H9 — Unpack firmware (.fw / .bin) -> .zip")
        self.geometry("640x320")
        self.resizable(False, False)
        self._build()

    def _build(self):
        f = ttk.Frame(self, padding=12); f.pack(fill="both", expand=True)
        ttk.Label(f, text="Firmware source (.fw or .bin):").grid(row=0, column=0, sticky="w")
        self.e_file = ttk.Entry(f, width=52)
        self.e_file.grid(row=0, column=1, padx=6)
        ttk.Button(f, text="Browse...", command=self.pick_file).grid(row=0, column=2)

        ttk.Label(f, text="Output .zip:").grid(row=1, column=0, sticky="w", pady=6)
        self.e_zip = ttk.Entry(f, width=52)
        self.e_zip.grid(row=1, column=1, padx=6)
        ttk.Button(f, text="Browse...", command=self.pick_zip).grid(row=1, column=2)

        ttk.Button(f, text="Unpack and create .zip", command=self.do_unpack).grid(row=2, column=0, columnspan=3, pady=12)

        self.txt = tk.Text(f, height=11, width=80, state="disabled")
        self.txt.grid(row=3, column=0, columnspan=3, pady=6)

    def log(self, s):
        self.txt.config(state="normal"); self.txt.insert("end", s + "\n")
        self.txt.config(state="disabled"); self.txt.see("end")

    def pick_file(self):
        p = filedialog.askopenfilename(title="Choose firmware", filetypes=[("Firmware", "*.fw *.bin"), ("All", "*.*")])
        if p:
            self.e_file.delete(0, "end"); self.e_file.insert(0, p)
            base = Path(p).with_suffix("")
            self.e_zip.delete(0, "end"); self.e_zip.insert(0, str(base) + "_unpacked.zip")

    def pick_zip(self):
        p = filedialog.asksaveasfilename(title="Save archive", defaultextension=".zip", filetypes=[("ZIP", "*.zip")])
        if p:
            self.e_zip.delete(0, "end"); self.e_zip.insert(0, p)

    def do_unpack(self):
        src = self.e_file.get().strip()
        dst = self.e_zip.get().strip()
        if not src or not os.path.isfile(src):
            messagebox.showerror("Error", "Please choose an existing .fw/.bin file"); return
        if not dst:
            messagebox.showerror("Error", "Please set the .zip output path"); return
        try:
            info = unpack_file(src, dst)
            for k, v in info.items():
                self.log(f"{k}: {v}")
            self.log("\nDone. Archive: " + dst)
            messagebox.showinfo("Done", "Unpack finished:\n" + dst)
        except Exception as ex:
            messagebox.showerror("Error", str(ex))
            self.log(f"ERROR: {ex}")


if __name__ == "__main__":
    App().mainloop()