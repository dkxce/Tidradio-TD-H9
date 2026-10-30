"""
==============================================================================
  AX.25 frame decoder/encoder
  Author:  dkxce (c)  https://github.com/dkxce/Tidradio-TD-H9
  Version: v1.1.0.0

  Russian:  Кодирование/декодирование бинарных AX.25-кадров в читаемый
            APRS-текст и обратно.
  English:  AX.25 binary frame encode/decode to/from readable APRS text.

  A KISS TNC like the TD-H9 sends, in the KISS payload, the full AX.25
  *information frame* in binary: an address block (dest / source / repeaters),
  a control byte, a PID byte and an information field (the actual APRS text).

  This module decodes just enough of the AX.25 UI-frame to reconstruct a plain
  callsign string of the form ``SRC>DST,REP1,REP2:info`` that can then be parsed
  by the APRS parser. It also builds such binary frames from text for TX.
==============================================================================
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

__author__ = "dkxce (c) https://github.com/dkxce/Tidradio-TD-H9"
__version__ = "v1.1.0.0"


@dataclass
class AX25Frame:
    """Decoded AX.25 frame. / Расшифрованный AX.25-кадр."""
    source: str = ""
    destination: str = ""
    repeaters: List[str] = field(default_factory=list)
    control: int = 0  # control field byte
    pid: Optional[int] = None
    info: bytes = b""
    is_ui: bool = False

    @property
    def header_text(self) -> str:
        """callsign header as 'SRC>DST,REP1,REP2' (no info)."""
        s = f"{self.source}>{self.destination}"
        if self.repeaters:
            s += "," + ",".join(self.repeaters)
        return s

    def to_text(self) -> str:
        """Full readable frame: header + ':' + info (decoded as ASCII)."""
        info = ""
        try:
            info = self.info.decode("ascii", errors="replace")
        except Exception:
            info = repr(self.info)
        if info:
            return f"{self.header_text}:{info}"
        return self.header_text


def _decode_callsign(addr: bytes) -> str:
    """Decode a 7-byte AX.25 address field into 'CALL' / 'CALL-SSID'.

    Russian:  Декодирует 7-байтное адресное поле AX.25 в позывной.
    English:  Decodes a 7-byte AX.25 address field into a callsign.
    """
    if not addr or len(addr) < 7:
        return ""
    chars = []
    for i in range(6):
        b = addr[i]
        if b == 0:
            continue
        c = chr(b >> 1)   # callsign chars are left-shifted by 1
        if c == " ":      # padded with spaces -> skip
            continue
        chars.append(c)
    call = "".join(chars)
    ssid = (addr[6] >> 1) & 0x0F  # SSID lives in bits 1-4 of byte 7
    if ssid:
        return f"{call}-{ssid}"
    return call


def decode_ax25(data: bytes) -> Optional[AX25Frame]:
    """Decode a raw AX.25 UI-frame payload into an AX25Frame.

    Returns None if the data is too short or is not a plausible AX.25 frame
    (e.g. it is already a plain-text APRS frame).

    Russian:  Разбирает бинарный AX.25-кадр в объект AX25Frame.
    English:  Parses a binary AX.25 frame into an AX25Frame object.
    """
    if not data or len(data) < 15:
        return None

    i = 0
    try:
        dest_bytes = data[i:i + 7]
        i += 7
        source_bytes = data[i:i + 7]
        i += 7
    except IndexError:
        return None

    # Validate: callsign chars must decode to printable letters/digits
    dst = _decode_callsign(dest_bytes)
    src = _decode_callsign(source_bytes)
    if not src or not dst:
        return None

    frame = AX25Frame(source=src, destination=dst)

    # Repeat (digipeater) addresses follow until the extended-flag is set
    # on the final address byte (bit0 == 1).
    ext = source_bytes[6] & 0x01
    while not (ext & 0x01):
        if i + 7 > len(data):
            break
        d = data[i:i + 7]
        i += 7
        frame.repeaters.append(_decode_callsign(d))
        ext = d[6] & 0x01

    if i >= len(data):
        return frame

    frame.control = data[i]
    i += 1

    # For UI frames (control 0x03) a protocol identifier byte follows.
    if frame.control & 0x01:  # odd => UI or unnumbered
        if i < len(data):
            frame.pid = data[i]
            i += 1
        frame.is_ui = True

    frame.info = data[i:]
    return frame


def _encode_callsign(call: str, ssid: int, last: bool) -> bytes:
    """Encode a 7-byte AX.25 address field for a callsign.

    Consumes 'CALL-7' or 'CALL' (SSID defaults to 0). Padding with spaces.

    Russian:  Кодирует позывной в 7-байтное адресное поле AX.25.
    English:  Encodes a callsign into a 7-byte AX.25 address field.
    """
    call = (call or "").strip()
    # Extract SSID from a trailing '-N' suffix.
    # Russian: извлекаем SSID из хвостового суффикса '-N'.
    dash = call.rfind("-")
    if dash != -1 and call[dash + 1:].isdigit():
        ssid = int(call[dash + 1:])
        call = call[:dash]
    elif dash != -1 and call[dash + 1:] == "":
        call = call[:dash]

    if len(call) > 6:
        call = call[:6]
    call = call.ljust(6, " ")
    out = bytearray()
    for ch in call:
        out.append(ord(ch) << 1)      # callsign chars are left-shifted by 1
    # final byte: raw ssid in bits 1-4, bit0 = last-address flag
    out.append(((ssid & 0x0F) << 1) | (1 if last else 0))
    return bytes(out)


def _parse_callsigns(text: str):
    """Parse 'SRC>DST,PATH' into (src, dst, [repeaters]).

    Everything after the first ':' (the info field) is ignored, so the
    function works on full frames 'SRC>DST,PATH:info' and on headers only.
    """
    text = (text or "").strip()
    # strip the info field if present
    colon = text.find(":")
    if colon != -1:
        text = text[:colon]
    arrow = text.find(">")
    if arrow == -1:
        return "", "", []
    src = text[:arrow].strip()
    rest = text[arrow + 1:].strip()
    parts = [p.strip() for p in rest.split(",") if p.strip()]
    dst = parts[0] if parts else ""
    repeaters = parts[1:]
    return src, dst, repeaters


def encode_ax25_text(text: str, default_dst: str = "APRS",
                     info_prefix: str = "") -> bytes:
    """Build a binary AX.25 UI-frame payload from an APRS text frame.

    ``text`` may be either a full frame 'SRC>DST,REP:info' or just 'SRC:info'
    / 'SRC'. The source callsign is the part before '>'.

    Russian:  Из текстового APRS-фрейма собирает бинарный AX.25-кадр.
    English:  Builds a binary AX.25 frame payload from an APRS text frame.
    """
    text = (text or "").strip()
    src, dst, repeaters = _parse_callsigns(text)
    if not src:
        raise ValueError("Source callsign missing (use 'CALL>...' or 'CALL')")

    if ":" in text:
        dummy, _, info = text.partition(":")
    else:
        # no ':' -> whole text is the header; info empty
        info = ""

    if not dst:
        dst = default_dst
    if info_prefix and info:
        info = info_prefix + info

    # Address block: dest, source, then zero or more digipeaters.
    # Russian: адресный блок — назначение, источник и ноль и более повторителей.
    if not repeaters:
        # only destination + source
        dest_bytes = _encode_callsign(dst, 0, False)
        src_bytes = _encode_callsign(src, 0, True)
        body = dest_bytes + src_bytes
    else:
        body = _encode_callsign(dst, 0, False) + _encode_callsign(src, 0, False)
        for i, _r in enumerate(repeaters):
            is_last = (i == len(repeaters) - 1)
            body += _encode_callsign(_r, 0, is_last)

    # control = 0x03 (UI), PID = 0xF0 (no layer 3)
    body += bytes([0x03, 0xF0])

    # info field must not exceed 256 bytes in practice; we simply append,
    # the TNC will handle the rest.
    body += info.encode("ascii", errors="replace")
    return body


def to_aprs_text(data: bytes) -> Optional[str]:
    """Convenience: decode AX.25 payload into readable 'SRC>DST,..:info' text.

    Returns decoded text, or falls back to the raw bytes as ASCII text if the
    payload does not look like a binary AX.25 frame.

    Russian:  Декодирует payload в читаемый APRS-текст.
    English:  Decodes payload into readable APRS text.
    """
    frame = decode_ax25(data)
    if frame is not None and frame.header_text:
        return frame.to_text()
    # not a recognized binary frame -> treat as text (e.g. "SRC>DST:info")
    try:
        return data.decode("ascii", errors="replace").strip()
    except Exception:
        return None