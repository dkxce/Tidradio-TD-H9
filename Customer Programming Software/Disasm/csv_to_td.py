import csv
import re
import sys

for _stream in (sys.stdout, sys.stderr, sys.stdin):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

CHANNEL_START = 16
CHANNEL_COUNT = 199
CHANNEL_SIZE = 16
CHNAME_START = 3392
CHNAME_SIZE = 8
CHINDEX_START = 6400
SCANINDEX_START = 6432
INDEX_LEN = 25

EMPTY_FREQ = b"\xff" * 4
EMPTY_TONE = b"\xff" * 2

POWER_MAP = {"low": 0, "mid": 1, "medium": 1, "high": 2}


def _freq_bytes(mhz):
    val = int(round(float(mhz) * 100000))
    if val <= 0 or val > 99999999:
        return None
    out = bytearray(4)
    for i in range(4):
        pair = val % 100
        val //= 100
        out[i] = ((pair // 10) << 4) | (pair % 10)
    return bytes(out)


def encode_freq(txt):
    txt = (txt or "").replace(",", ".").strip()
    if not txt:
        return None
    try:
        return _freq_bytes(txt)
    except (ValueError, TypeError):
        return None


def ctcss_bytes(txt):
    txt = (txt or "").strip()
    if not txt:
        return None
    try:
        code = int(round(float(txt.replace(",", ".")) * 10))
    except (ValueError, TypeError):
        return None
    if code < 670 or code > 2541:
        return None
    s = "%04d" % code
    return bytes([int(s[2:4], 16), int(s[0:2], 16)])


def dcs_bytes(txt, polarity=""):
    digits = re.sub(r"\D", "", (txt or "").strip())
    if len(digits) != 3:
        return None
    h, t, u = int(digits[0]), int(digits[1]), int(digits[2])
    if max(h, t, u) > 7:
        return None
    inv = (polarity or "").strip().upper().startswith("I")
    return bytes([(t << 4) | u, ((0xC if inv else 0x8) << 4) | h])


def encode_tone(txt, polarity=""):
    txt = (txt or "").strip()
    if not txt or txt.upper() == "OFF":
        return EMPTY_TONE
    if txt[0].upper() == "D":
        body = txt
        inline_pol = ""
        if body[-1] in ("N", "n", "I", "i"):
            inline_pol = body[-1].upper()
            body = body[:-1]
        b = dcs_bytes(body, inline_pol or polarity)
        if b is None:
            return EMPTY_TONE
        return b
    b = ctcss_bytes(txt)
    if b is None:
        return EMPTY_TONE
    return b


def encode_name(name, buf, offset):
    raw = (name or "").encode("gb2312", errors="replace")
    raw = raw[:CHNAME_SIZE]
    for i in range(CHNAME_SIZE):
        buf[offset + i] = raw[i] if i < len(raw) else 0xFF


def _yset(value):
    return (value or "").strip().lower() in ("on", "yes", "1", "true", "y")


def build_channel(rx, tx, rx_tone, tx_tone, power, bandwidth, scrambler,
                  ptt_id, freq_hop, busy_lock, rx_model, warn):
    rx_bytes = encode_freq(rx)
    if rx_bytes is None:
        raise ValueError("Неверная RX-частота: %r" % rx)
    tx_bytes = encode_freq(tx) if tx and str(tx).strip() else EMPTY_FREQ
    if tx_bytes is None:
        tx_bytes = EMPTY_FREQ

    rx_tone_b = encode_tone(rx_tone)
    tx_tone_b = encode_tone(tx_tone)

    pw = POWER_MAP.get((power or "").strip().lower())
    if pw is None:
        warn.append("Неизвестная мощность %r -> Low" % power)
        pw = 0

    flag_model = 1 if rx_model and rx_model.strip().lower() in ("am",) else 0
    if rx_model and rx_model.strip().lower() not in ("fm", "am", ""):
        warn.append("Неизвестная модуляция %r -> FM" % rx_model)
        flag_model = 0
    reserved = flag_model & 3

    ptt = {"off": 0, "begin": 1, "end": 2, "both": 3}.get((ptt_id or "").strip().lower())
    if ptt is None:
        warn.append("PTT ID %r -> Off" % ptt_id)
        ptt = 0

    flags1 = (ptt << 6) | (0x20 if _yset(freq_hop) else 0) | (0x04 if _yset(busy_lock) else 0)

    narrow = (bandwidth or "").strip().lower() == "narrow"
    flags2 = (pw << 4) | (0x08 if narrow else 0)

    try:
        scr = int(scrambler)
    except (ValueError, TypeError):
        scr = 0
    scr = max(0, min(16, scr))

    ch = bytearray(
        rx_bytes + tx_bytes + rx_tone_b + tx_tone_b
        + bytes([scr, flags1, flags2, reserved])
    )
    if len(ch) != CHANNEL_SIZE:
        raise ValueError("Ошибка размера канала")
    return bytes(ch)


def _col(headers, *names):
    norm = [h.strip().lower().replace("_", " ") for h in headers]
    for exact in (True, False):
        for n in names:
            key = n.strip().lower().replace("_", " ")
            for i, h in enumerate(norm):
                if (h == key) if exact else (key in h):
                    return i
    return -1


CANONICAL_SCHEMA = [
    ("num",       "Channel No",    ["channel no", "channel", "ch", "location", "no", "number", "#"]),
    ("rx",        "RX Freq [MHz]", ["rx freq", "rx frequency", "receive frequency", "frequency rx"]),
    ("tx",        "TX Freq [MHz]", ["tx freq", "tx frequency", "transmit frequency", "frequency tx"]),
    ("rx_tone",   "RX CTCSS/DCS",  ["rx ctcss", "rx ctcss/dcs", "rx tone", "rx subaudio", "rx dcs"]),
    ("tx_tone",   "TX CTCSS/DCS",  ["tx ctcss", "tx ctcss/dcs", "tx tone", "tx subaudio", "tx dcs"]),
    ("power",     "Power",         ["pwr", "power", "lmh", "power level", "output power", "output"]),
    ("bandwidth", "Bandwidth",     ["bw", "bandwidth", "band width", "band"]),
    ("scrambler", "Scrambler",     ["src", "scrambler", "scramble", "scrambling"]),
    ("ptt_id",    "PTT ID",        ["ptt id", "pttid", "ptt"]),
    ("freq_hop",  "Freq Hop",      ["freq hop", "frequency hop", "hop"]),
    ("busy_lock", "Busy Lock",     ["bl", "busy lock", "busy"]),
    ("scan",      "Scan",          ["scan", "scan add", "scanlist", "scanning"]),
    ("rx_model",  "Rx Modulation", ["rx modulation", "rx model", "modulation", "receive modulation", "rx mode"]),
    ("name",      "Channel Name",  ["channel name", "name", "display", "display name", "alias", "label"]),
]

REQUIRED_PARAMS = {"num", "rx"}


def _prompt_column(colmap, headers, param, label):
    required = param in REQUIRED_PARAMS
    print("Параметр '%s' не найден среди колонок." % label)
    if required:
        print("  Он обязательный. Введите номер колонки из списка выше.")
    else:
        print("  Введите номер колонки из списка выше либо 0/Enter, чтобы пропустить (значение по умолчанию).")
    for _ in range(8):
        try:
            raw = input("  > ").strip()
        except EOFError:
            raw = ""
        if raw == "":
            if required:
                if param == "num":
                    colmap[param] = None
                    print("  Channel No пропущен: номера будут назначены по порядку.")
                    return
                print("  Обязательный параметр '%s' нельзя пропустить." % label)
                continue
            colmap[param] = None
            print("  %s пропущен (по умолчанию)." % label)
            return
        try:
            n = int(raw)
        except ValueError:
            print("  Введите целый номер колонки.")
            continue
        if n == 0:
            if required:
                print("  Обязательный параметр '%s' нельзя пропустить." % label)
                continue
            colmap[param] = None
            print("  %s пропущен (по умолчанию)." % label)
            return
        if not (1 <= n <= len(headers)):
            print("  Номер вне диапазона 1..%d." % len(headers))
            continue
        idx = n - 1
        if idx in colmap.values():
            print("  Колонка '[%d] %s' уже используется другим параметром." % (n, headers[idx]))
            continue
        colmap[param] = idx
        print("  %s -> колонка [%d] %s" % (label, n, headers[idx]))
        return
    colmap[param] = None
    if required:
        raise ValueError("Не удалось сопоставить обязательный параметр '%s'" % label)


def _resolve_schema(headers, interactive=None):
    if interactive is None:
        interactive = sys.stdin.isatty()
    norm = [h.strip().lower().replace("_", " ") for h in headers]
    colmap = {}
    issues = []
    claims = {}

    for param, label, aliases in CANONICAL_SCHEMA:
        keys = [a.strip().lower().replace("_", " ") for a in aliases]
        exact_hits = [i for i, h in enumerate(norm) if h in keys]
        sub_hits = [i for i, h in enumerate(norm) if h not in keys and any(k in h for k in keys)]
        hits = exact_hits or sub_hits
        if not hits:
            colmap[param] = None
            issues.append("Нет колонки для параметра '%s'" % label)
            continue
        chosen = hits[0]
        colmap[param] = chosen
        claims.setdefault(chosen, []).append(label)
        if len(hits) > 1:
            issues.append(
                "Неоднозначность '%s': подходят колонки %s"
                % (label, ", ".join("[%d] %s" % (i + 1, headers[i]) for i in hits))
            )

    for i, labs in claims.items():
        if len(labs) > 1:
            issues.append("Колонка '[%d] %s' используется параметрами: %s" % (i + 1, headers[i], ", ".join(labs)))

    missing = [p for p, l, _ in CANONICAL_SCHEMA if colmap[p] is None]

    if issues or missing:
        print("Колонки CSV (%d):" % len(headers))
        for i, h in enumerate(headers):
            print("  [%d] %s" % (i + 1, h))
        for it in issues:
            print("  КОЛЛИЗИЯ: %s" % it)

    if interactive and missing:
        for param, label, _ in CANONICAL_SCHEMA:
            if colmap[param] is None:
                _prompt_column(colmap, headers, param, label)

    print("Сопоставление колонок:")
    for param, label, _ in CANONICAL_SCHEMA:
        idx = colmap[param]
        if idx is None:
            print("  %-16s -> <не задано>" % label)
        else:
            print("  %-16s -> [%d] %s" % (label, idx + 1, headers[idx]))
    return colmap


def parse_rows(path):
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        header = next(reader)
    header = [h.strip() for h in header]

    if _col(header, "rx freq", "frequency [mhz]") >= 0:
        return _parse_canonical(path, header), "canonical"
    if _col(header, "frequency") >= 0 and _col(header, "duplex") >= 0:
        return _parse_chirp(path, header), "chirp"
    return _parse_canonical(path, header), "canonical"


def _parse_canonical(path, header):
    colmap = _resolve_schema(header)
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        next(reader)

        ncols = len(header)
        fallback_num = 0
        rows = []

        def val(row, p):
            i = colmap.get(p)
            return row[i] if i is not None and i < len(row) else ""

        for row in reader:
            if not any(v.strip() for v in row):
                continue
            row += [""] * (ncols - len(row))
            if colmap.get("num") is not None:
                num = _int(val(row, "num"))
            else:
                fallback_num += 1
                num = fallback_num
            rows.append({
                "num": num,
                "rx": val(row, "rx"),
                "tx": val(row, "tx"),
                "rx_tone": val(row, "rx_tone"),
                "tx_tone": val(row, "tx_tone"),
                "power": val(row, "power"),
                "bandwidth": val(row, "bandwidth"),
                "scrambler": val(row, "scrambler"),
                "ptt_id": val(row, "ptt_id"),
                "freq_hop": val(row, "freq_hop"),
                "busy_lock": val(row, "busy_lock"),
                "scan": val(row, "scan"),
                "rx_model": val(row, "rx_model"),
                "name": val(row, "name"),
            })
        return rows


def _parse_chirp(path, header):
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        next(reader)
        c_ch = _col(header, "location")
        c_name = _col(header, "name")
        c_freq = _col(header, "frequency")
        c_dup = _col(header, "duplex")
        c_off = _col(header, "offset")
        c_tone = _col(header, "tone")
        c_rtone = _col(header, "rtonefreq")
        c_ctone = _col(header, "ctonefreq")
        c_dcs = _col(header, "dtcscode")
        c_pol = _col(header, "dtcspolarity")
        c_rxdcs = _col(header, "rxdtcscode")
        c_mode = _col(header, "mode")
        c_skip = _col(header, "skip")
        c_pwr = _col(header, "power")
        width = max(c for c in (c_freq, c_dup, c_off, c_rtone, c_ctone, c_dcs) if c >= 0) + 1

        rows = []
        for row in reader:
            if not any(v.strip() for v in row):
                continue
            row += [""] * (width - len(row))
            rx = row[c_freq] if c_freq >= 0 else ""
            dup = (row[c_dup] if c_dup >= 0 else "").strip().lower()
            off = (row[c_off] if c_off >= 0 else "").strip()
            rx_v = _float(rx)
            tx = rx
            if rx_v is not None:
                if dup == "+" and _float(off) is not None:
                    tx = rx_v + _float(off)
                elif dup == "-" and _float(off) is not None:
                    tx = rx_v - _float(off)
                elif dup == "split" and _float(off) is not None:
                    tx = _float(off)
            tx = "" if tx in (None, 0) else ("%f" % round(float(tx), 6) if isinstance(tx, float) else tx)

            rtone = row[c_rtone] if c_rtone >= 0 else ""
            ctone = row[c_ctone] if c_ctone >= 0 else ""
            dcs = (row[c_dcs] if c_dcs >= 0 else "") or (row[c_rxdcs] if c_rxdcs >= 0 else "")
            pol = row[c_pol] if c_pol >= 0 else ""
            dcs_digits = re.sub(r"\D", "", dcs)
            if len(dcs_digits) >= 3:
                suffix = "I" if pol.strip().upper().startswith("I") else "N"
                rx_tone = tx_tone = "D" + dcs_digits + suffix
            elif rtone or ctone:
                rx_tone = tx_tone = (ctone or rtone)
            else:
                rx_tone = tx_tone = ""

            mode = (row[c_mode] if c_mode >= 0 else "").strip().lower()
            rx_model = "AM" if mode == "am" else "FM"
            bandwidth = "Narrow" if mode == "nfm" else "Wide"
            skip = (row[c_skip] if c_skip >= 0 else "").strip()
            scan = "No" if skip in ("*", "skip") else "Yes"
            pwr = row[c_pwr] if c_pwr >= 0 else ""
            power = "High"
            if "low" in pwr.lower():
                power = "Low"
            elif "mid" in pwr.lower():
                power = "Mid"

            rows.append({
                "num": int(row[c_ch]) if c_ch >= 0 and _int(row[c_ch]) else None,
                "rx": ("%f" % rx_v) if rx_v is not None else "",
                "tx": tx,
                "rx_tone": rx_tone,
                "tx_tone": tx_tone,
                "power": power,
                "bandwidth": bandwidth,
                "scrambler": "0",
                "ptt_id": "Off",
                "freq_hop": "Off",
                "busy_lock": "Off",
                "scan": scan,
                "rx_model": rx_model,
                "name": row[c_name] if c_name >= 0 else "",
            })
        return rows


def _int(v):
    try:
        return int(str(v).strip())
    except (ValueError, TypeError):
        return None


def _float(v):
    try:
        return float(str(v).replace(",", ".").strip())
    except (ValueError, TypeError):
        return None


def _set_bit(bitmap, idx, on):
    byte_idx = idx // 8
    if byte_idx >= len(bitmap):
        return
    bit = 1 << (idx % 8)
    if on:
        bitmap[byte_idx] |= bit
    else:
        bitmap[byte_idx] &= ~bit


def patch(td_path, rows, out_path):
    with open(td_path, "rb") as f:
        data = bytearray(f.read())
    if len(data) < CHANNEL_START + CHANNEL_SIZE * CHANNEL_COUNT:
        raise ValueError("Целевой .td слишком короткий")

    chindex = data[CHINDEX_START:CHINDEX_START + INDEX_LEN]
    scanindex = data[SCANINDEX_START:SCANINDEX_START + INDEX_LEN]
    warns = []
    written = 0

    for row in rows:
        num = row.get("num")
        if num is None or not (1 <= num <= CHANNEL_COUNT):
            warns.append("Пропуск: номер канала вне 1..%d: %s" % (CHANNEL_COUNT, num))
            continue
        idx = num - 1
        try:
            ch = build_channel(
                row.get("rx", ""), row.get("tx", ""),
                row.get("rx_tone", ""), row.get("tx_tone", ""),
                row.get("power", ""), row.get("bandwidth", ""),
                row.get("scrambler", ""), row.get("ptt_id", ""),
                row.get("freq_hop", ""), row.get("busy_lock", ""),
                row.get("rx_model", ""), warns,
            )
        except ValueError as e:
            warns.append("Канал %d: %s" % (num, e))
            continue
        base = CHANNEL_START + idx * CHANNEL_SIZE
        data[base:base + CHANNEL_SIZE] = ch
        encode_name(row.get("name", ""), data, CHNAME_START + idx * CHNAME_SIZE)
        _set_bit(chindex, idx, True)
        _set_bit(scanindex, idx, _yset(row.get("scan")))
        written += 1

    data[CHINDEX_START:CHINDEX_START + INDEX_LEN] = chindex
    data[SCANINDEX_START:SCANINDEX_START + INDEX_LEN] = scanindex

    with open(out_path, "wb") as f:
        f.write(bytes(data))
    return written, warns


def main():
    if len(sys.argv) < 3:
        print("Использование: python csv_to_td.py <input.csv> <target.td> [output.td]")
        return 1
    csv_path = sys.argv[1]
    td_path = sys.argv[2]
    out_path = sys.argv[3] if len(sys.argv) > 3 else td_path.rsplit(".", 1)[0] + "_patched.td"
    try:
        rows, fmt = parse_rows(csv_path)
        written, warns = patch(td_path, rows, out_path)
        print("Формат CSV: %s" % fmt)
        print("Каналов записано: %d -> %s" % (written, out_path))
        for w in warns:
            print("  WARN: %s" % w)
    except Exception as e:
        print("Ошибка: %s" % e, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())