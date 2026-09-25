import csv
import sys

CHANNEL_START = 16
CHANNEL_COUNT = 199
CHANNEL_SIZE = 16
CHNAME_START = 3392
CHNAME_SIZE = 8
CHINDEX_START = 6400
SCANINDEX_START = 6432
INDEX_LEN = 25

HEADER = [
    "Channel No",
    "RX Freq [MHz]",
    "TX Freq [MHz]",
    "RX CTCSS/DCS",
    "TX CTCSS/DCS",
    "Power",
    "Bandwidth",
    "Scrambler",
    "PTT ID",
    "Freq Hop",
    "Busy Lock",
    "Scan",
    "Rx Modulation",
    "Channel Name",
]

POWER_MAP = {0: "Low", 1: "Mid", 2: "High"}
PTT_ID_MAP = {0: "Off", 1: "Begin", 2: "End", 3: "Both"}
RX_MODEL_MAP = {0: "FM", 1: "AM"}


def decode_freq(b):
    if not b or len(b) < 4 or all(x in (0x00, 0xFF) for x in b):
        return None
    val = 0
    for i, bb in enumerate(b[:4]):
        hi, lo = (bb >> 4) & 0xF, bb & 0xF
        if hi > 9 or lo > 9:
            return None
        val += (hi * 10 + lo) * (100 ** i)
    if val <= 0:
        return None
    return val / 100000.0


def decode_tone(b):
    if not b or len(b) < 2:
        return "OFF"
    if (b[0] in (0x00, 0xFF)) or (b[1] in (0x00, 0xFF)):
        return "OFF"
    pol = b[1] >> 4
    if pol >= 8:
        hundreds = b[1] & 0xF
        tens = (b[0] >> 4) & 0xF
        units = b[0] & 0xF
        suffix = "I" if pol == 0xC else "N"
        return "D%d%d%d%s" % (hundreds, tens, units, suffix)
    s = "%02X%02X" % (b[1], b[0])
    if not all(c in "0123456789" for c in s):
        return "OFF"
    return "%.1f" % (int(s) / 10.0)


def bit_is_set(bitmap, idx):
    byte_idx = idx // 8
    if byte_idx >= len(bitmap):
        return False
    return (bitmap[byte_idx] >> (idx % 8)) & 1


def decode_name(raw):
    data = raw[:CHNAME_SIZE] if isinstance(raw, bytes) else bytes(raw)
    end = 0
    for i, c in enumerate(data):
        if c in (0x00, 0xFF):
            end = i
            break
    else:
        end = len(data)
    return data[:end].decode("gb2312", errors="replace").strip()


def read_channels(data):
    if len(data) < CHANNEL_START + CHANNEL_SIZE:
        raise ValueError("Файл слишком короткий, чтобы содержать каналы")
    chindex = data[CHINDEX_START:CHINDEX_START + INDEX_LEN]
    scanindex = data[SCANINDEX_START:SCANINDEX_START + INDEX_LEN]
    rows = []
    for i in range(CHANNEL_COUNT):
        base = CHANNEL_START + i * CHANNEL_SIZE
        if base + CHANNEL_SIZE > len(data):
            break
        ch = data[base:base + CHANNEL_SIZE]
        rxfreq = decode_freq(ch[0:4])
        if rxfreq is None:
            continue
        txfreq = decode_freq(ch[4:8])
        rxtone = decode_tone(ch[8:10])
        txtone = decode_tone(ch[10:12])
        scrambler = ch[12]
        flags1 = ch[13]
        flags2 = ch[14]
        reserved = ch[15]
        ptt_id = PTT_ID_MAP.get((flags1 >> 6) & 3, "")
        freq_hop = "On" if flags1 & 0x20 else "Off"
        busy_lock = "On" if flags1 & 0x04 else "Off"
        power = POWER_MAP.get((flags2 >> 4) & 3, "")
        bandwidth = "Narrow" if flags2 & 0x08 else "Wide"
        rx_model = RX_MODEL_MAP.get(reserved & 3, "")
        scan = "Yes" if bit_is_set(scanindex, i) else "No"
        name_offset = CHNAME_START + i * CHNAME_SIZE
        name = decode_name(data[name_offset:name_offset + CHNAME_SIZE])
        rows.append([
            i + 1,
            "%.5f" % rxfreq,
            "%.5f" % txfreq if txfreq is not None else "",
            rxtone,
            txtone,
            power,
            bandwidth,
            scrambler,
            ptt_id,
            freq_hop,
            busy_lock,
            scan,
            rx_model,
            name,
        ])
    return rows


def convert(td_path, csv_path):
    with open(td_path, "rb") as f:
        data = f.read()
    rows = read_channels(data)
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(HEADER)
        writer.writerows(rows)
    print("Каналов записано: %d -> %s" % (len(rows), csv_path))
    return len(rows)


def main():
    if len(sys.argv) < 2:
        print("Использование: python td_to_csv.py <file.td> [output.csv]")
        return 1
    td_path = sys.argv[1]
    csv_path = sys.argv[2] if len(sys.argv) > 2 else td_path.rsplit(".", 1)[0] + ".csv"
    try:
        convert(td_path, csv_path)
    except Exception as e:
        print("Ошибка: %s" % e, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())