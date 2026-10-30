"""
==============================================================================
  Minimal APRS packet parser for human-readable display
  Author:  dkxce (c)  https://github.com/dkxce/Tidradio-TD-H9
  Version: v1.1.0.0

  Russian:  Простой парсер APRS-пакетов для отображения в окне.
  English:  Minimal APRS packet parser for display purposes.

  Handles the standard APRS UI-frame fields that the Odmaster app exchanges:
  source callsign, destination, digipeater path, strings starting with '>',
  message '::' frames and position data. Not a full APRS-spec implementation,
  but enough to show incoming packets in the GUI.
==============================================================================
"""

from __future__ import annotations

from dataclasses import dataclass, field

__author__ = "dkxce (c) https://github.com/dkxce/Tidradio-TD-H9"
__version__ = "v1.1.0.0"


@dataclass
class APRSMessage:
    """Result of parsing one APRS frame. / Результат разбора одного APRS-кадра."""
    source: str = ""
    destination: str = ""
    path: str = ""
    infotype: str = ""
    comment: str = ""
    data_type: str = "?"
    position_lat: str = ""
    position_lon: str = ""
    raw: str = ""

    def to_multiline(self) -> str:
        """Return a multi-line summary for the RX window."""
        # Russian: возвращает многострочное представление для окна приёма.
        pos = ""
        if self.position_lat and self.position_lon:
            pos = f"\n    Position: {self.position_lat} {self.position_lon}"
        return (f"From: {self.source}\n"
                f"  To: {self.destination}\n"
                f"  Path: {self.path or '-'}\n"
                f"  Type: {self.data_type}  ({self.infotype})\n"
                f"  Info: {self.comment or ''}{pos}\n"
                f"  Raw: {self.raw}")


def parse_aprs(txt: str) -> APRSMessage:
    """Parse a single APRS text frame into an APRSMessage.

    Russian:  Разбирает один APRS-текстовый кадр в объект APRSMessage.
    English:  Parses one APRS text frame into an APRSMessage.
    """
    m = APRSMessage(raw=txt)
    txt = txt.strip()
    # remove trailing newline / control chars
    txt = txt.split("\r")[0].split("\n")[0]

    colon = txt.find(":")
    if colon == -1:
        m.comment = txt
        return m

    header = txt[:colon]
    info = txt[colon + 1:]

    # Split source/destination/path from the header part 'SRC>DST,PATH'.
    # Russian: разделяем источник/назначение/путь из заголовка 'SRC>DST,PATH'.
    arrow = header.find(">")
    if arrow != -1:
        m.source = header[:arrow]
        rest = header[arrow + 1:]
        if "," in rest:
            dst, path = rest.split(",", 1)
            m.destination = dst
            m.path = path
        else:
            m.destination = rest

    m.comment = info

    # try to detect message frames
    if info.startswith("::"):
        # message:  ::DESTCALL:THE MESSAGE
        rest = info[2:]
        dst, _, body = rest.partition(":")
        m.data_type = "M"
        m.infotype = "Message"
        m.destination = dst.strip() or m.destination
        m.comment = body
    else:
        # detect position-ish frames
        first_char = info[:1]
        m.data_type = first_char
        type_names = {
            "!": "Position without timestamp",
            "/": "Position with timestamp",
            ">": "Status",
            "#": "Weather",
            ";": "Object",
            ")": "Item",
            ":": "Message",
            "{": "User-defined",
            "}": "Third-party",
            "`": "Position (no timestamp)",
            "@": "Position with timestamp",
            "?": "Query",
            "<": "Autoposition",
        }
        m.infotype = type_names.get(first_char, first_char)

        # crude lat/lon extraction for '/'- or '!'-style positions
        # pattern:  /040000Z4903.50N/07201.75W/
        if first_char in "!/`@":
            body = info[1:]
            # skip timestamp if present (6 digits + suffix)
            i = 0
            if first_char in "/@":
                # ddhhmmZ or ddhhmmz
                if len(body) >= 7:
                    i = 7
            # latitude DDMM.MMN or DDMM.MMS (8 chars)
            for j, ch in enumerate(body[i:]):
                if ch.isdigit() or ch == ".":
                    continue
                else:
                    non_digits = j   # NOQA - offset to latitude start
                    break
            # find latitude: 8 chars starting with digits, then N/S
            for start in range(i, len(body)):
                if body[start:start + 4].isdigit():
                    lat8 = body[start:start + 8]
                    if len(lat8) == 8 and body[start + 7] in "NSns":
                        m.position_lat = lat8
                        lon8 = body[start + 9: start + 9 + 9]
                        if len(lon8) == 9 and lon8[8] in "EWew":
                            m.position_lon = lon8[:8] + lon8[8]
                        try:
                            rest = body[start + 9 + 9:]
                            m.comment = rest.lstrip("/")
                        except Exception:
                            pass
                        break
                break

    return m