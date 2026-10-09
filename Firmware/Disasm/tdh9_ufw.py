# -*- coding: utf-8 -*-
"""
Shared TD-H9 (AC695X) UFW / raw-image helpers.

Provides parsing of the UFW container, XOR decryption of the app area,
and rebuilding of both the .fw container and the raw .bin flash image.

The parameters that were hard-coded for the v1.0.33 build (APP_BASE, APP_SIZE,
MD5_DATA, MD5_HEADER, ...) are now AUTO-DETECTED from the image itself, so a
different firmware version should also work. If detection fails, the known
v1.0.33 values are used as a fallback and a warning flag is raised.

Round-trips are verified against the stock image (see test scripts).
"""

import struct
import hashlib

UFW_KEY = 0xF181
CHIP_KEY = 0xF181

# ---- Fallback layout of the stock v1.0.33 build (used only if detection fails) ----
FALLBACK_APP_AREA_BASE = 0x5000        # start of the app area inside the flash image
FALLBACK_APP_HEADER = 0x5020           # app.bin section header (first CRC field)
FALLBACK_APP_BASE = 0x5100             # app code base inside the app area
FALLBACK_APP_SIZE = 0xCF5EC            # app.bin length
FALLBACK_MD5_DATA = 0xD5102            # ascii MD5 of app.bin
FALLBACK_MD5_HEADER = 0xD50E2          # crc16 container header for the md5 field
FALLBACK_APP_AREA_DATA_SIZE = 0xCF6CC


def crc16(data, crc=0):
    """CRC16-CCITT (poly 0x1021), used across the whole format."""
    for b in data:
        crc ^= (b << 8) & 0xFFFF
        for _ in range(8):
            crc = (((crc << 1) ^ (0x1021 if crc & 0x8000 else 0)) & 0xFFFF)
    return crc


def _jl_enc(buf, off, size, key):
    """JChip/AC695X XOR stream cipher (incremental CRC-derived key). Modifies buf in place."""
    for i in range(size):
        buf[off + i] ^= (key & 0xFF)
        key = ((key << 1) ^ (0x1021 if key & 0x8000 else 0)) & 0xFFFF


# ---------------------------------------------------------------------------
# Decryption / parsing
# ---------------------------------------------------------------------------

def decrypt_app_area(inner: bytes) -> bytes:
    """Decrypt the app area (0x5000..end) of a raw flash image, return decrypted bytes."""
    dec = bytearray(inner)
    for off in range(FALLBACK_APP_AREA_BASE, len(dec), 32):
        size = min(32, len(dec) - off)
        key = CHIP_KEY ^ ((off - FALLBACK_APP_AREA_BASE) >> 2)
        _jl_enc(dec, off, size, key)
    return bytes(dec)


def parse_ufw_header(fw: bytes):
    """Parse the UFW header. Returns (plain_header_bytes, num_entries).
    The returned header has both the fixed part and the entry block decrypted."""
    if len(fw) < 0x200:
        raise ValueError("file smaller than 0x200 bytes - not an UFW image")
    hdr = bytearray(fw[:0x200])
    _jl_enc(hdr, 0, 0x40, UFW_KEY)              # decrypt fixed header part
    hdr_crc, list_crc, image_size, n, unk, hsize, chip = struct.unpack_from("<HHIHHI48s", hdr, 0)
    if hsize != 0x200:
        raise ValueError(f"unexpected header size 0x{hsize:X}")
    if n <= 0 or 0x40 + n * 0x50 > len(hdr):
        raise ValueError(f"invalid entry count n={n}")
    for off in range(0x40, 0x40 + n * 0x50, 0x50):
        _jl_enc(hdr, off, 0x50, UFW_KEY)        # decrypt entry block
    return hdr, n


def ufw_entries(hdr_plain: bytes, n: int):
    """Yield (rel_offset, entry_dict) for every UFW entry."""
    for off in range(0x40, 0x40 + n * 0x50, 0x50):
        rec = struct.unpack_from("<HHHHIII44s16s", hdr_plain, off)
        yield off - 0x40, {
            "etype": rec[0], "eindex": rec[1], "edcrc": rec[2], "ewa1": rec[3],
            "eoffset": rec[4], "esize": rec[5], "esize2": rec[6], "ewa2": rec[7],
            "name": rec[8].split(b"\0", 1)[0].decode("ascii", "ignore"),
        }


def get_flash_inner(fw: bytes) -> bytes:
    """Extract the raw flash.bin blob from an UFW container."""
    hdr, n = parse_ufw_header(fw)
    for _, e in ufw_entries(hdr, n):
        if e["name"] == "flash.bin":
            return bytes(fw[e["eoffset"]: e["eoffset"] + e["esize"]])
    raise ValueError("no flash.bin entry found")


# ---------------------------------------------------------------------------
# Layout auto-detection
# ---------------------------------------------------------------------------

def detect_layout(dec: bytes):
    """Auto-detect app layout from a DECRYPTED app area (starts at 0x5000).

    Returns a dict with keys: app_area_base, app_base, app_size, md5_data, md5_header,
    app_area_data_size, plus a boolean 'ok' and a human 'note'.

    Heuristics used (common to AC695X / TD-H9 builds):
      - the app-area header table at 0x5000 contains a section named "app.bin";
        the 4-byte field at section+8 gives APP_SIZE;
      - APP_BASE is the first code word right after the 0x100-byte section table
        (section table spans 0x5000..0x5100);
      - the ascii MD5 of app.bin is stored right after a "md5.bin" marker string;
      - the MD5_HEADER is the 32-byte container ending right before that MD5 text
        (contains the crc16 of the MD5 text at +2).
    """
    app_area_base = FALLBACK_APP_AREA_BASE
    if len(dec) < 0x6000 or dec[app_area_base:app_area_base + 4] == b"\xff\xff\xff\xff":
        return {
            "ok": False, "note": "no app-area header found",
            **fallback_layout(), "app_area_base": app_area_base,
        }

    # 1) APP_SIZE from the 'app.bin' section descriptor
    app_size = None
    app_header = None
    mark = b"app.bin\x00"
    pos = dec.find(mark, app_area_base, app_area_base + 0x2000)
    if pos >= 0:
        # the section header (crc/size fields) is 0x10 bytes before the name string
        app_header = pos - 0x10
        v = struct.unpack_from("<I", dec, app_header + 8)[0]
        if 0x1000 < v < len(dec):
            app_size = v

    # 2) APP_BASE = section table end = app_area_base + 0x100
    app_base = app_area_base + 0x100

    # 3) MD5_DATA from the 'md5.bin' section header (the one that stores the MD5 text).
    # NOTE: resource paths like '.../res/md5.bin' also appear in the string pool, so we
    # must pick the occurrence whose following bytes actually hold a 32-hex MD5 text.
    md5_data = None
    md5_header = None
    pos = app_area_base
    while True:
        pos = dec.find(b"md5.bin\x00", pos)
        if pos < 0:
            break
        # locate a 32-hex MD5 text within the following 0x40 bytes
        import re as _re
        m = _re.search(rb"[0-9a-f]{32}", dec[pos: pos + 0x40])
        if m and m.start() > 0:      # the MD5 must not start immediately (there is a small header gap)
            md5_data = pos + m.start()
            md5_header = md5_data - 0x20
            break
        pos += 9

    # If MD5 marker not found, fall back to known offset derived from app end (v1.0.33 only)
    if md5_data is None and app_size:
        # md5 sits at (app_base+app_size+0x1016) in v1.0.33; keep conservative -> use fallback
        md5_data = FALLBACK_MD5_DATA
        md5_header = FALLBACK_MD5_HEADER

    ok = app_size is not None
    base = {
        "app_area_base": app_area_base,
        "app_header": app_header if app_size else FALLBACK_APP_HEADER,
        "app_base": app_base if app_size else FALLBACK_APP_BASE,
        "app_size": app_size if app_size else FALLBACK_APP_SIZE,
        "md5_data": md5_data if md5_data else FALLBACK_MD5_DATA,
        "md5_header": md5_header if md5_header else FALLBACK_MD5_HEADER,
        "app_area_data_size": (app_size + 0xE0) if app_size else FALLBACK_APP_AREA_DATA_SIZE,
    }
    base["ok"] = ok
    base["note"] = ("detected app.bin size descriptor" if ok else
                    "detection failed; using v1.0.33 fallback layout")
    return base


def _is_md5_text(b: bytes) -> bool:
    if len(b) < 32:
        return False
    return all(c in b"0123456789abcdef" for c in b[:32])


def fallback_layout():
    return {
        "app_header": FALLBACK_APP_HEADER,
        "app_base": FALLBACK_APP_BASE,
        "app_size": FALLBACK_APP_SIZE,
        "md5_data": FALLBACK_MD5_DATA,
        "md5_header": FALLBACK_MD5_HEADER,
        "app_area_data_size": FALLBACK_APP_AREA_DATA_SIZE,
    }


# ---------------------------------------------------------------------------
# Build / pack
# ---------------------------------------------------------------------------

def extract_app_bin(inner_flash: bytes, layout=None) -> tuple[bytes, dict]:
    """Extract and decrypt app.bin from a raw flash image. Returns (app_bytes, layout)."""
    dec = decrypt_app_area(inner_flash)
    lay = layout or detect_layout(dec)
    app = bytes(dec[lay["app_base"]: lay["app_base"] + lay["app_size"]])
    return app, lay


def make_app_inner_flash(inner_flash: bytes, new_app: bytes, layout=None) -> bytes:
    """Write a modified app.bin back into a raw flash image (recomputing CRC/MD5).
    Returns the new full raw flash image."""
    if len(new_app) > layout["app_size"]:
        raise ValueError(f"app.bin larger than 0x{layout['app_size']:X} bytes")
    new_app = new_app.ljust(layout["app_size"], b"\xFF")[:layout["app_size"]]

    dec = bytearray(decrypt_app_area(inner_flash))
    app_base = layout["app_base"]

    # write the new app into the decrypted area
    dec[app_base: app_base + len(new_app)] = new_app

    # recompute CRC16 of app.bin and store in its section header
    app_crc = crc16(new_app)
    hdr = layout["app_header"]  # app.bin section header
    struct.pack_into("<H", dec, hdr + 2, app_crc)
    struct.pack_into("<H", dec, hdr, crc16(dec[hdr + 2: hdr + 32]))

    # recompute MD5 ascii + its crc16 container
    md5_text = hashlib.md5(new_app).hexdigest().encode("ascii")
    md5_data = layout["md5_data"]
    md5_header = layout["md5_header"]
    dec[md5_data: md5_data + 32] = md5_text
    struct.pack_into("<H", dec, md5_header + 2, crc16(md5_text))
    struct.pack_into("<H", dec, md5_header, crc16(dec[md5_header + 2: md5_header + 32]))

    # recompute CRC16 of the whole app data area + its header
    area_data_size = layout["app_area_data_size"]
    area_crc = crc16(dec[app_base - 0x100 + 0x20: app_base - 0x100 + 0x20 + area_data_size])
    area_base = layout["app_area_base"]
    struct.pack_into("<H", dec, area_base + 2, area_crc)
    struct.pack_into("<H", dec, area_base, crc16(dec[area_base + 2: area_base + 32]))

    # re-encrypt: flip only the bytes that changed
    old_dec = decrypt_app_area(inner_flash)
    out = bytearray(inner_flash)
    for i, (a, b) in enumerate(zip(old_dec, dec)):
        if a != b:
            out[i] ^= a ^ b
    return bytes(out)


def build_ufw(inner_flash: bytes, orig_fw: bytes) -> bytes:
    """Wrap a full raw flash image into an UFW container, based on an original .fw.
    Returns the ready-to-flash .fw bytes."""
    fw = bytearray(orig_fw)
    hdr, n = parse_ufw_header(fw)
    replaced = False
    for idx, e in ufw_entries(hdr, n):
        if e["name"] == "flash.bin":
            fw[e["eoffset"]: e["eoffset"] + len(inner_flash)] = inner_flash
            struct.pack_into("<H", hdr, 0x40 + idx * 0x50 + 4, crc16(inner_flash))
            replaced = True
    if not replaced:
        raise ValueError("flash.bin entry not found")

    # rebuild the header: entry list CRC then header CRC, then re-encrypt
    entry_area = bytearray(hdr[0x40: 0x40 + n * 0x50])
    enc_entries = bytearray(entry_area)
    for rel in range(0, len(enc_entries), 0x50):
        _jl_enc(enc_entries, rel, 0x50, UFW_KEY)
    struct.pack_into("<H", hdr, 2, crc16(enc_entries))
    struct.pack_into("<H", hdr, 0, crc16(hdr[2: 0x40]))
    # final encryption of the whole header
    for off in range(0x40, 0x40 + n * 0x50, 0x50):
        _jl_enc(hdr, off, 0x50, UFW_KEY)
    _jl_enc(hdr, 0, 0x40, UFW_KEY)
    fw[:0x200] = hdr
    return bytes(fw)


def is_stock_inner(inner_flash: bytes) -> bool:
    """Return True if the raw flash image matches the known stock v1.0.33 SHA-256."""
    return hashlib.sha256(inner_flash).hexdigest() == \
        "d0df607441a44765127cd5f00e34398f5866712dff3dfb17dc6f1fbf81118dc0"