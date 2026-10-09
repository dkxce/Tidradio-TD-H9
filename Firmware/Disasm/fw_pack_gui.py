#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fw_pack_gui.py — build TD-H9 firmware images from an edited app.bin or from a .zip
created by fw_unpack_gui.py.

The app.bin is expected to be edited with a hex editor (e.g. HxD).

Input (one of):
  1) a .zip produced by fw_unpack_gui.py — the extracted app.bin is used.
  2) a .app.bin file — a new/modified application image.

Outputs:
  - .fw   (UFW container)            — flashed over USB.
  - .bin  (raw flash image)          — flashed via CH340/CH341.

The layout parameters are auto-detected; a stock .fw is only needed as the
container template (it is found automatically next to the script or input).

Run:  python fw_pack_gui.py
"""
import os
import sys
import hashlib
import zipfile
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import tdh9_ufw as U


def load_new_app(src: str) -> tuple[bytes, str]:
    """Return (new_app_bytes, description). Supports .zip and raw app.bin."""
    srcp = Path(src)
    if srcp.suffix.lower() == ".zip":
        with zipfile.ZipFile(srcp) as z:
            names = z.namelist()
            if "app.bin" in names:
                return z.read("app.bin"), "app.bin from zip"
            for n in names:
                if n.endswith(".bin") and ("app" in n.lower() or "dec" in n.lower()):
                    return z.read(n), n
            raise ValueError("No app.bin found in the zip")
    else:
        return srcp.read_bytes(), srcp.name


def pack(src_path: str, out_fw: str, out_bin: str) -> dict:
    """Build .fw and .bin from an edited app.bin / zip. Returns an info dict."""
    new_app, how = load_new_app(src_path)

    # Find a stock .fw to act as the UFW container template.
    stock_fw = find_stock_fw(src_path)
    if stock_fw is None:
        raise ValueError("No stock .fw found to build the container. "
                         "Put a stock TD-H9-V1.0.33.fw next to the script or input.")

    inner = U.get_flash_inner(stock_fw)
    # Auto-detect layout from the stock image, then validate app.bin length.
    _, layout = U.extract_app_bin(inner)
    if len(new_app) > layout["app_size"]:
        raise ValueError(f"app.bin larger than 0x{layout['app_size']:X} bytes "
                         f"(this firmware's app size)")
    new_app = new_app.ljust(layout["app_size"], b"\xFF")[:layout["app_size"]]

    # Inject the new app into the raw flash image (recomputes CRC/MD5).
    new_inner = U.make_app_inner_flash(inner, new_app, layout)

    # Build the .fw container and write both outputs.
    fw_data = U.build_ufw(new_inner, stock_fw)
    Path(out_fw).write_bytes(fw_data)
    Path(out_bin).write_bytes(new_inner)

    return {
        "app source": how,
        "layout note": layout.get("note", "?"),
        "detected app_size": hex(layout["app_size"]),
        "new app MD5": hashlib.md5(new_app).hexdigest(),
        "new flash SHA-256": hashlib.sha256(new_inner).hexdigest(),
        "new .fw SHA-256": hashlib.sha256(fw_data).hexdigest(),
        "new .bin SHA-256": hashlib.sha256(new_inner).hexdigest(),
        "new .fw path": os.path.abspath(out_fw),
        "new .bin path": os.path.abspath(out_bin),
    }


def find_stock_fw(src_path: str):
    """Locate a stock .fw template: next to the script or input.

    Returns the raw bytes of the .fw, or None.
    """
    candidates = [
        HERE / "TD-H9-V1.0.33.fw",
        Path(src_path).parent / "TD-H9-V1.0.33.fw",
        Path(src_path).with_suffix(".fw"),
    ]
    for c in candidates:
        if c and c.is_file() and c.suffix.lower() == ".fw":
            d = c.read_bytes()
            try:
                U.parse_ufw_header(d)          # raises if not a valid UFW
                U.get_flash_inner(d)
                return d
            except Exception:
                continue
    return None


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("TD-H9 — Build firmware (app.bin / zip -> .fw + .bin)")
        self.geometry("700x360")
        self.resizable(False, False)
        self._build()

    def _build(self):
        f = ttk.Frame(self, padding=12); f.pack(fill="both", expand=True)
        ttk.Label(f, text="Source (zip or edited app.bin):").grid(row=0, column=0, sticky="w")
        self.e_src = ttk.Entry(f, width=54)
        self.e_src.grid(row=0, column=1, padx=6)
        ttk.Button(f, text="Browse...", command=self.pick_src).grid(row=0, column=2)

        ttk.Label(f, text="Stock .fw (container template):").grid(row=1, column=0, sticky="w", pady=6)
        self.e_fw = ttk.Entry(f, width=54)
        self.e_fw.grid(row=1, column=1, padx=6)
        ttk.Button(f, text="Auto / Browse...", command=self.pick_fw).grid(row=1, column=2)

        ttk.Label(f, text="Save .fw to:").grid(row=2, column=0, sticky="w")
        self.e_ofw = ttk.Entry(f, width=54)
        self.e_ofw.grid(row=2, column=1, padx=6)
        ttk.Button(f, text="Browse...", command=self.pick_ofw).grid(row=2, column=2)

        ttk.Label(f, text="Save .bin to:").grid(row=3, column=0, sticky="w", pady=6)
        self.e_obin = ttk.Entry(f, width=54)
        self.e_obin.grid(row=3, column=1, padx=6)
        ttk.Button(f, text="Browse...", command=self.pick_obin).grid(row=3, column=2)

        ttk.Button(f, text="Build .fw and .bin", command=self.do_pack).grid(row=4, column=0, columnspan=3, pady=12)

        self.txt = tk.Text(f, height=8, width=84, state="disabled")
        self.txt.grid(row=5, column=0, columnspan=3)

    def log(self, s):
        self.txt.config(state="normal"); self.txt.insert("end", s + "\n")
        self.txt.config(state="disabled"); self.txt.see("end")

    def pick_src(self):
        p = filedialog.askopenfilename(title="Choose zip or app.bin",
                                       filetypes=[("ZIP / app.bin", "*.zip *.bin"), ("All", "*.*")])
        if p:
            self.e_src.delete(0, "end"); self.e_src.insert(0, p)
            base = Path(p).with_suffix("")
            if not self.e_ofw.get():
                self.e_ofw.insert(0, str(base.parent / (base.stem + "_new.fw")))
            if not self.e_obin.get():
                self.e_obin.insert(0, str(base.parent / (base.stem + "_new.bin")))

    def pick_fw(self):
        p = filedialog.askopenfilename(title="Stock .fw", filetypes=[("FW", "*.fw")])
        if p:
            self.e_fw.delete(0, "end"); self.e_fw.insert(0, p)

    def pick_ofw(self):
        p = filedialog.asksaveasfilename(defaultextension=".fw", filetypes=[("FW", "*.fw")])
        if p: self.e_ofw.delete(0, "end"); self.e_ofw.insert(0, p)

    def pick_obin(self):
        p = filedialog.asksaveasfilename(defaultextension=".bin", filetypes=[("BIN", "*.bin")])
        if p: self.e_obin.delete(0, "end"); self.e_obin.insert(0, p)

    def do_pack(self):
        src = self.e_src.get().strip()
        if not src or not os.path.isfile(src):
            messagebox.showerror("Error", "Please choose an existing zip or app.bin"); return
        stock = self.e_fw.get().strip()
        try:
            info = pack(src, self.e_ofw.get().strip() or "out.fw",
                        self.e_obin.get().strip() or "out.bin")
            for k, v in info.items():
                self.log(f"{k}: {v}")
            self.log("\nDone.")
            messagebox.showinfo("Done", "Built:\n" + info["new .fw path"] + "\n" + info["new .bin path"])
        except Exception as ex:
            messagebox.showerror("Error", str(ex))
            self.log(f"ERROR: {ex}")


if __name__ == "__main__":
    App().mainloop()