#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TD-H9: read codeplug from the radio via COM and save as .td.

Protocol (based on as TIDRadioCPS DMR/OpenGD77Form.cs):

  Handshake (PerformHandshake):
    -> 50 56 4F 4A 4B 5C 14          ("PVOJK\\x5c\\x14")
    <- 06
    -> 02
    <- <up to 32 bytes: model/version hex>        (radio sends ~8 bytes)
    -> 06
    <- 06

  Read EEPROM (ReadDataNewProtocol):
    -> 52 addr_hi addr_lo 20                      ('R', addr16, 32)
    <- 57 addr_hi addr_lo 20  <32 bytes data> [<1 trailing byte>]
    Response frame = 4-byte header + 32 data (CPS reads 37 bytes total).
    Data are the bytes at response[4:36].

  CPS stores each 32-byte chunk at CommsBuffer[addr] -- by address, so bytes
  land on their true offsets (no shift).

  Save .td (MainForm save -> DataToByte):
    - 65536-byte array filled with 0xFF
    - bytes 0..7   : model marker "MD-760P" + 0xFF
    - channels @0x10    (199 x 16)
    - names     @0x0D40 (199 x 8)
    - chindex   @0x1900, scan @0x1920, VFO A/B @0x1950/0x1960,
      DTMF @0x1800, boot @0x1C00, mic @0x1F20, misc @0x1F28...
    - everything else stays 0xFF

Requires:   pip install pyserial
Run:        python read_tdh9_serial.py --port COM6
Notepad++:  cmd /k cd /d "$(CURRENT_DIRECTORY)" & "C:\Python3.10.9\Python.exe" "$(FILE_NAME)"
Notepad++:  cmd /k cd /d "$(CURRENT_DIRECTORY)" & "C:\Python3.10.9\Python.exe" "$(FILE_NAME)" --port COM6
"""

import sys
import os
import time
import json
import struct
import argparse

try:
    import serial
    import serial.tools.list_ports
except ImportError:
    sys.exit("pyserial not installed. Run: pip install pyserial")

# ---------------------------------------------------------------------------
# Protocol constants
# ---------------------------------------------------------------------------
BAUD      = 38400
HANDSHAKE = bytes([0x50, 0x56, 0x4F, 0x4A, 0x4B, 0x5C, 0x14])  # PVOJK\x5c\x14
CMD_READ  = 0x52   # 'R'
CMD_RESP  = 0x57   # 'W'
BLOCK     = 32

# ---------------------------------------------------------------------------
# .td layout (DMR/CpsAddrCfg.cs)
# ---------------------------------------------------------------------------
TD_SIZE       = 0x10000
MODEL_MARKER  = b"MD-760P"          # 7 bytes; 8th = 0xFF

CHANNEL_START   = 0x0010            # 199 channels x 16 bytes
CHANNEL_LEN     = 3184              # 199 * 16
CHNAME_START    = 0x0D40            # 199 names x 8 bytes
CHNAME_LEN      = 1592
CHINDEX_START   = 0x1900            # channel valid bits (25 bytes)
SCANINDEX_START = 0x1920
VFO_A_START     = 0x1950
VFO_B_START     = 0x1960
DTMF_STUN       = 0x1800
DTMF_KILL       = 0x1810
BOOT_MSG_START  = 0x1C00
MIC_GAIN        = 0x1F20
LANGUAGE        = 0x1F28
DISPLAY_STYLE   = 0x1F29
MENU_COLOR      = 0x1F2A
VFO_SCAN_UPPER  = 0x1F2B
VFO_SCAN_LOWER  = 0x1F2D
SCAN_HANG       = 0x1F2F
READ_START      = 0x0000
READ_LEN        = 0x3220                  # 12832 bytes (>= CPS_FULL_BUFFER_SIZE 12564)


def list_ports_verbose():
    print("Available serial ports:")
    for p in serial.tools.list_ports.comports():
        print("  %-10s vid=%-5s pid=%-5s  %s" % (p.device, p.vid, p.pid, p.description))
    print()


def find_com_port():
    ports = list(serial.tools.list_ports.comports())
    for p in ports:
        d = ((p.description or '') + ' ' + (p.manufacturer or '')).lower()
        if p.vid in (0x1A86, 0x16C0, 0x10C4) or any(k in d for k in ('jieli', 'tidradio', 'radio')):
            return p.device
        if p.vid == 1659 and p.pid == 8963: # PL2303
            return p.device
    return None


class Radio:
    def __init__(self, port):
        self.ser = serial.Serial()
        self.ser.port = port
        self.ser.baudrate = BAUD
        self.ser.bytesize = serial.EIGHTBITS
        self.ser.parity = serial.PARITY_NONE
        self.ser.stopbits = serial.STOPBITS_ONE
        self.ser.timeout = 1.0
        self.ser.write_timeout = 2.0
        self.ser.dtr = True
        self.ser.rts = True
        self.ser.open()
        self.ser.reset_input_buffer()

    def rx_available(self, max_n, wait=0.4):
        """Read whatever arrives within `wait` sec, up to max_n bytes."""
        data = bytearray()
        deadline = time.time() + wait
        while len(data) < max_n and time.time() < deadline:
            chunk = self.ser.read(max_n - len(data))
            if chunk:
                data.extend(chunk)
        return bytes(data)

    def rx_exact(self, n, timeout=2.0):
        data = bytearray()
        deadline = time.time() + timeout
        while len(data) < n:
            if time.time() > deadline:
                break
            chunk = self.ser.read(min(n - len(data), 64))
            if chunk:
                data.extend(chunk)
        return bytes(data)

    def handshake(self):
        self.ser.reset_input_buffer()
        self.ser.write(HANDSHAKE)
        r = self.rx_exact(1)
        if not r or r[0] != 0x06:
            raise RuntimeError("handshake: no 0x06 (got %r)" % r.hex())
        self.ser.write(b'\x02')
        ver = self.rx_available(64, wait=0.5)
        self.ser.write(b'\x06')
        r = self.rx_exact(1)
        if not r or r[0] != 0x06:
            raise RuntimeError("handshake step3: no 0x06")
        return ver

    def read_block(self, addr):
        """Read 32 bytes at addr. Frame: 57 hi lo 20 + 32 data + trailing."""
        cmd = bytes([CMD_READ, (addr >> 8) & 0xFF, addr & 0xFF, BLOCK])
        self.ser.write(cmd)
        # CPS reads 37 bytes = 4 header + 32 data + 1 trailing; data at [4:36]
        resp = self.rx_available(4 + BLOCK + 1, wait=0.4)
        if len(resp) < 4 + BLOCK:
            raise RuntimeError("read @0x%04X: short resp (%d bytes)" % (addr, len(resp)))
        hdr = resp[0:4]
        if hdr[0] != CMD_RESP or hdr[1] != cmd[1] or hdr[2] != cmd[2] or hdr[3] != cmd[3]:
            raise RuntimeError("read @0x%04X: bad hdr %s" % (addr, hdr.hex()))
        data = resp[4:4 + BLOCK]
        # drain any extra trailing bytes so the next frame starts clean
        extra = resp[4 + BLOCK:]
        if not extra:
            time.sleep(0.02)
            self.ser.read(8)
        return bytes(data)

    def read_comms_buffer(self, start=READ_START, length=READ_LEN):
        """Fill CommsBuffer[addr] with each 32-byte chunk (as CPS does)."""
        buf = bytearray([0xFF]) * TD_SIZE
        n = length // BLOCK
        for i in range(n):
            addr = start + i * BLOCK
            blk = self.read_block(addr)
            buf[addr:addr + BLOCK] = blk
            if (i + 1) % 64 == 0 or i == n - 1:
                print("  read 0x%04X..0x%04X  (%d%%)" % (start, addr + BLOCK, (i + 1) * 100 // n))
        return bytes(buf)

    def close(self):
        try:
            self.ser.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# .td assembly (mirrors DataToByte)
# ---------------------------------------------------------------------------

def build_td(comms):
    """Assemble .td:
      - bytes 0x0000..0xEA70 are pre-filled with 0x00 (firmware requirement)
      - data blocks (channels/names/config) are written on top at fixed offsets
      - model marker "MD-760P"+FF at 0..7
      - everything above 0xEA70 stays 0xFF
    """
    td = bytearray([0xFF]) * TD_SIZE
    # zero-fill the codeplug data area 0x0010..0xEA70 (firmware requirement)
    td[0x0010:0xEA70] = bytes(0xEA70 - 0x0010)
    # model marker: "MD-760P" + 0xFF in bytes 0..7
    td[0:8] = MODEL_MARKER + b"\xff"
    # channels
    td[CHANNEL_START:CHANNEL_START + CHANNEL_LEN] = comms[CHANNEL_START:CHANNEL_START + CHANNEL_LEN]
    # names
    td[CHNAME_START:CHNAME_START + CHNAME_LEN] = comms[CHNAME_START:CHNAME_START + CHNAME_LEN]
    # config blocks 0x1800..0x1F30 (dtmf, chindex, scan, vfo, boot, misc)
    td[0x1800:0x1F30] = comms[0x1800:0x1F30]
    return bytes(td)


# ---------------------------------------------------------------------------
# Parse / display helpers
# ---------------------------------------------------------------------------

def decode_cstr(buf, off, n):
    s = buf[off:off + n]
    out = []
    for b in s:
        if b == 0 or b == 0xFF:
            break
        out.append(chr(b))
    return ''.join(out)


def bcd_mhz(buf, off):
    val = 0
    mul = 1
    for k in range(4):
        hi = buf[off + k] >> 4
        lo = buf[off + k] & 0xF
        if hi > 9 or lo > 9:
            return None
        val += (hi * 10 + lo) * mul
        mul *= 100
    return val / 100000.0


def parse_settings(td):
    res = {}
    res['boot_msg1']     = decode_cstr(td, BOOT_MSG_START + 00, 16)
    res['boot_msg2']     = decode_cstr(td, BOOT_MSG_START + 16, 16)
    res['boot_msg3']     = decode_cstr(td, BOOT_MSG_START + 32, 16)
    res['mic_gain']      = td[MIC_GAIN]
    res['language']      = td[LANGUAGE]
    res['display_style'] = td[DISPLAY_STYLE]
    res['menu_color']    = td[MENU_COLOR]
    res['scan_hang']     = td[SCAN_HANG]
    res['vfo_a_rx_mhz']  = bcd_mhz(td, VFO_A_START + 0)
    res['vfo_a_tx_mhz']  = bcd_mhz(td, VFO_A_START + 4)
    res['vfo_b_rx_mhz']  = bcd_mhz(td, VFO_B_START + 0)
    res['vfo_b_tx_mhz']  = bcd_mhz(td, VFO_B_START + 4)
    res['dtmf_stun']     = decode_cstr(td, DTMF_STUN, 16)
    res['dtmf_kill']     = decode_cstr(td, DTMF_KILL, 16)

    chans = []
    for i in range(199):
        off = CHANNEL_START + i * 16
        rx = bcd_mhz(td, off)
        tx = bcd_mhz(td, off + 4)
        name = decode_cstr(td, CHNAME_START + i * 8, 8)
        if rx or tx or name:
            chans.append({'ch': i + 1, 'rx_mhz': rx, 'tx_mhz': tx, 'name': name})
    res['channels'] = chans
    return res


def main():
    ap = argparse.ArgumentParser(description='TD-H9: read codeplug via COM -> .td')
    ap.add_argument('--port', default=None, help='COM port (auto-detect if omitted)')
    ap.add_argument('--td', default='tdh9_dump.td', help='output .td file')
    ap.add_argument('--json', default='tdh9_settings.json', help='output settings JSON')
    ap.add_argument('--raw', default=None, help='save raw 64K comms buffer')
    args = ap.parse_args()

    list_ports_verbose()
    port = args.port or find_com_port()
    if not port:
        print("No COM port found. Use --port COMx")
        return 1
    print("Using port:", port)

    r = Radio(port)
    try:
        ver = r.handshake()
        print("Handshake OK. version:", ver.hex(' ').upper())

        print("Reading EEPROM 0x%04X..0x%04X..." % (READ_START, READ_START + READ_LEN))
        comms = r.read_comms_buffer(READ_START, READ_LEN)
        if args.raw:
            open(args.raw, 'wb').write(comms)
            print("Saved raw comms buffer:", args.raw)

        td = build_td(comms)
        with open(args.td, 'wb') as f:
            f.write(td)
        print("Saved .td:", args.td, "(%d bytes)" % len(td))

        settings = parse_settings(td)
        with open(args.json, 'w', encoding='utf-8') as f:
            json.dump(settings, f, ensure_ascii=False, indent=2, default=str)
        print("Saved settings:", args.json)

        print("\n=== Key settings ===")
        for k in ('boot_msg1', 'boot_msg2', 'boot_msg3', 'vfo_a_rx_mhz', 'vfo_b_rx_mhz',
                  'mic_gain', 'language', 'display_style', 'dtmf_stun'):
            print("  %-16s = %r" % (k, settings.get(k)))
        print("\n=== Channels ===")
        for c in settings['channels']:
            print("  CH %-3d %-10r %-10r %-10r" % (c['ch'], c['rx_mhz'], c['tx_mhz'], c['name']))
    finally:
        r.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())