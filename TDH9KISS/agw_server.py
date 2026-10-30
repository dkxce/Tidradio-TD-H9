"""
==============================================================================
  AGWPE TCP/IP server (SV2AGW / Dire Wolf compatible, 36-byte framing)
  Author:  dkxce (c)  https://github.com/dkxce/Tidradio-TD-H9
  Version: v1.1.0.0

  Russian:  Сервер, совместимый с протоколом AGWPE TCP/IP. К нему
            подключаются APRS-приложения (YaAC, APRSIS32, UI-View, AgwpePort
            и др.) как к AGW-движку. Формат сверен с реализацией Dire Wolf
            (src/server.c, src/agwlib.c).
  English:  AGWPE TCP/IP compatible server. Format matches Dire Wolf.

  AGWPE frame header (36 bytes):
      portx(1) res(3) datakind(1) res(1) pid(1) res(1)
      call_from(10) call_to(10) data_len(4 LE) user_reserved(4

  datakind is an ASCII character. Common frame types:
      Client -> Server:
        'P' login (ignored)     'R' version request
        'G' port info request   'g' port caps request
        'X' register callsign   'x' unregister
        'm' toggle monitor      'k' toggle raw frames
        'V' transmit UI (via)   'M' transmit UI (no via)
        'K' transmit raw AX.25  'C'/'D'/'d' connected-mode
      Server -> Client:
        'R' version reply       'G' port info reply
        'g' port caps reply     'X' register ack
        'U' monitored unproto   'I' monitored connected
        'S' monitored supervisory / other unnum.
        'T' own transmitted     'K' raw AX.25 frame
        'C'/'D'/'d' connected-mode events

  TX 'V'/'M' data layout (per Dire Wolf):
      [1 byte number of digipeaters][10 bytes each digi][info part]
  TX 'K' data layout:
      [1 byte TNC port indicator - ignored][raw AX.25 frame]
  RX 'U' monitor payload (per Dire Wolf):
      " 1:Fm SRC To DST Via DIGIS <UI pid=F0 Len=N >[HH:MM:SS]\r" + info + "\r\0"
      (sent only after the client toggles monitoring with 'm')

  Version reply (Dire Wolf uses AGWPE 2005/127, stored as 4-byte big-endian
  ints so that clients reading 'H2xH2x' get major=2005, minor=127).
==============================================================================
"""

from __future__ import annotations

import socket
import struct
import threading
import time
from typing import Callable, Optional

from ax25 import decode_ax25, encode_ax25_text

__author__ = "dkxce (c) https://github.com/dkxce/Tidradio-TD-H9"
__version__ = "v1.1.0.0"

HEADER_SIZE = 36
_HEADER_FMT = "BxxxBxBx10s10sIxxxx"

# AGWPE software version we advertise.
AGW_MAJOR = 2005
AGW_MINOR = 127

# Data kind characters (client -> server)
K_LOGIN = b"P"
K_VERSION = b"R"
K_PORT_INFO = b"G"
K_PORT_CAPS = b"g"
K_REGISTER = b"X"
K_UNREGISTER = b"x"
K_MONITOR = b"m"
K_RAW = b"k"
K_SEND_UNPROTO = b"M"     # UI without digis
K_SEND_UNPROTO_VIA = b"V"  # UI with digis
K_SEND_RAW = b"K"
K_CONNECT = b"C"
K_CONNECT_VIA = b"v"
K_SEND_DATA = b"D"
K_DISCONNECT = b"d"

# Data kind characters (server -> client)
K_VERSION_REPLY = b"R"
K_PORT_INFO_REPLY = b"G"
K_PORT_CAPS_REPLY = b"g"
K_REGISTER_ACK = b"X"
K_MON_UNPROTO = b"U"
K_MON_CONNECTED = b"I"
K_MON_SUPV = b"S"
K_MON_OWN = b"T"
K_RAW_FRAME = b"K"

# TX-capable kinds
TX_KINDS = {b"M", b"V", b"K"}


def _build_header(port: int, kind: bytes, pid: int, call_from: str,
                  call_to: str, data_len: int) -> bytes:
    """Build a 36-byte AGWPE header.

    Russian:  Собирает 36-байтный заголовок AGWPE.
    English:  Builds a 36-byte AGWPE header.
    """
    cf = call_from.encode("utf-8", "replace")[:10].ljust(10, b"\x00")
    ct = call_to.encode("utf-8", "replace")[:10].ljust(10, b"\x00")
    return struct.pack(_HEADER_FMT, port, ord(kind), pid, cf, ct, data_len)


def _parse_header(buf: bytes):
    """Parse a 36-byte header; return (port, kind_str, pid, from, to, len)."""
    port, kind, pid, call_from, call_to, data_len = struct.unpack(
        _HEADER_FMT, buf[:HEADER_SIZE])
    return (port, chr(kind), pid,
            call_from.decode("utf-8", "replace").rstrip("\x00"),
            call_to.decode("utf-8", "replace").rstrip("\x00"),
            data_len)


class AGW_TCPServer:
    """AGWPE TCP/IP server exposing the radio as an AGW engine.

    Russian:  AGW-совместимый TCP-сервер, предоставляющий радио как AGW-движок.
    English:  AGW-compatible TCP server exposing the radio as an AGW engine.
    """

    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 8000,
        on_rx_from_client: Optional[Callable[[bytes], None]] = None,
        on_forward_to_client: Optional[Callable[[bytes], None]] = None,
        on_clients_change: Optional[Callable[[], None]] = None,
        station_callsign: str = "TNC1",
    ):
        self.host = host
        self.port = port
        # Called with raw AX.25/APRS bytes to transmit to the radio.
        self.on_rx_from_client = on_rx_from_client
        # Called for debug/info with the bytes sent to clients.
        self.on_forward_to_client = on_forward_to_client
        # Called when a client connects or disconnects.
        # Russian: вызывается при подключении/отключении клиента.
        self.on_clients_change = on_clients_change
        self.station_callsign = station_callsign

        self.port_name = "TNC1"
        self.port_baud = 1200  # advertised baud (used for port caps)

        # Optional debug callback: (kind, cfrom, cto, pid, data)
        self._debug_cb = None

        self._sock: Optional[socket.socket] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._clients: set = set()
        # Per-client state: monitor enabled / raw enabled / registered calls.
        self._client_flags: dict = {}
        self._lock = threading.Lock()

    # ---------------------------------------------------------------- lifecycle
    def start(self):
        # Russian: запуск слушающего сокета в фоновом потоке.
        # English: starts the listening socket in a background thread.
        if self._running:
            return
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind((self.host, self.port))
        self._sock.listen(8)
        self._running = True
        self._thread = threading.Thread(target=self._accept_loop, daemon=True)
        self._thread.start()

    def stop(self):
        # Russian: остановка сервера и закрытие всех клиентов.
        # English: stops the server and closes all clients.
        self._running = False
        with self._lock:
            for c in list(self._clients):
                try:
                    c.close()
                except Exception:
                    pass
            self._clients.clear()
            self._client_flags.clear()
        if self._sock is not None:
            try:
                self._sock.close()
            except Exception:
                pass

    @property
    def address(self) -> str:
        return f"{self.host}:{self.port}"

    @property
    def client_count(self) -> int:
        with self._lock:
            return len(self._clients)

    def client_list(self) -> list:
        """Return per-client info for display.

        AGW clients are all capable of TX; callsign is unknown ('').

        Russian:  Возвращает список клиентов для отображения.
        """
        with self._lock:
            out = []
            for conn in list(self._clients):
                try:
                    ra, rp = conn.getpeername()[:2]
                except Exception:
                    ra, rp = "?", 0
                out.append({"addr": ra, "port": rp, "callsign": "", "can_tx": True})
            return out

    # ----------------------------------------------------------------- internal
    def _accept_loop(self):
        while self._running:
            try:
                conn, _addr = self._sock.accept()
            except Exception:
                break
            with self._lock:
                self._clients.add(conn)
                self._client_flags[conn] = {"monitor": False, "raw": False}
            if self.on_clients_change is not None:
                try:
                    self.on_clients_change()
                except Exception:
                    pass
            threading.Thread(target=self._handle_client, args=(conn,),
                             daemon=True).start()

    def _handle_client(self, conn: socket.socket):
        # Russian: читаем фреймы AGW (36-байтный заголовок + данные).
        # English: reads AGW frames (36-byte header + data).
        buf = b""
        try:
            conn.settimeout(60)
            while self._running:
                try:
                    data = conn.recv(4096)
                except socket.timeout:
                    continue
                if not data:
                    break
                buf += data
                while len(buf) >= HEADER_SIZE:
                    datalen = struct.unpack_from("<I", buf, 28)[0]
                    total = HEADER_SIZE + datalen
                    if len(buf) < total:
                        break
                    frame = buf[:total]
                    buf = buf[total:]
                    self._process_frame(conn, frame)
        except Exception:
            pass
        finally:
            self._remove_client(conn)

    def _send_frame(self, conn, port, kind, pid, cfrom, cto, payload=b""):
        """Send one complete AGW frame to a client."""
        hdr = _build_header(port, kind, pid, cfrom, cto, len(payload))
        try:
            conn.sendall(hdr + payload)
        except Exception:
            pass

    def _process_frame(self, conn, frame: bytes):
        """Parse and dispatch one full AGW frame from a client."""
        try:
            port, kind, pid, cfrom, cto, datalen = _parse_header(frame[:HEADER_SIZE])
        except Exception:
            return
        data = frame[HEADER_SIZE:HEADER_SIZE + datalen]

        # -- debug hook (optional): dump every incoming frame from the client
        if self._debug_cb is not None:
            try:
                self._debug_cb(kind, cfrom, cto, pid, data)
            except Exception:
                pass

        # --- version request: reply with AGWPE version (2005/127)
        if kind == "R":
            ver = struct.pack(">II", AGW_MAJOR, AGW_MINOR)
            self._send_frame(conn, 0, K_VERSION_REPLY, 0, "", "", ver)
            return

        # --- port info request: expose a single TNC port
        if kind == "G":
            payload = b"\x00;" + self.port_name.encode("utf-8") + b";"
            self._send_frame(conn, 0, K_PORT_INFO_REPLY, 0, "", "", payload)
            return

        # --- port capabilities request
        if kind == "g":
            # 12 bytes: 8B + 1 uint (baud, traffic, txdelay, txtail, persist,
            # slot, maxframe, conns, bytes_received) - see pyham-pe _PCAPS_FMT.
            baud_code = self._baud_code(self.port_baud)
            caps = struct.pack(
                "<8BI",
                baud_code,  # baud rate code
                0,          # traffic level
                50,         # tx delay (x10 ms -> 500 ms)
                1,          # tx tail
                64,         # persist
                50,         # slot time
                230,        # max frame length
                0,          # active connections
                0,          # bytes received (uint32)
            )
            self._send_frame(conn, port, K_PORT_CAPS_REPLY, 0, "", "", caps)
            return

        # --- callsign registration: confirm with a 1-byte result (1 = ok)
        if kind == "X":
            self._send_frame(conn, 0, K_REGISTER_ACK, 0, cfrom, "", b"\x01")
            return

        # --- monitor / raw toggles
        if kind == "m":
            with self._lock:
                self._client_flags[conn]["monitor"] = \
                    not self._client_flags[conn]["monitor"]
            return

        if kind == "k":
            with self._lock:
                self._client_flags[conn]["raw"] = \
                    not self._client_flags[conn]["raw"]
            return

        # --- login: no response expected
        if kind == "P":
            return

        # --- transmit requests: forward to the radio
        if kind in ("M", "V", "K"):
            self._tx_to_radio(conn, kind, cfrom, cto, pid, data)
            return

        if kind in ("C", "v", "D", "d", "x"):
            # connected-mode & unregister: not supported for APRS-only; ignore.
            return

    # ------------------------------------------------------------------ TX part
    def _tx_to_radio(self, conn, kind, cfrom, cto, pid, data):
        """Forward an outgoing frame to the BLE radio.

        Format (per Dire Wolf server.c):
          'M' (no digis): data = info text directly (no ndigi prefix).
          'V' (digis):    data = [1 byte ndigi][10 bytes per digi][info].
          'K' (raw):      data = [1 byte TNC indicator][raw AX.25 frame].

        Russian:  Передаёт исходящий кадр в радио по BLE.
        English:  Forwards an outgoing frame to the radio over BLE.
        """
        payload = None
        if kind == "K" and len(data) >= 2:
            # raw frame: skip the first (TNC indicator) byte
            payload = bytes(data[1:])
        elif kind == "M":
            # 'M' has NO digipeater prefix: data IS the info text.
            info = bytes(data).decode("utf-8", "replace")
            text = f"{cfrom}>{cto}:{info}"
            try:
                payload = encode_ax25_text(text)
            except Exception:
                payload = bytes(data)
        elif kind == "V" and len(data) >= 1:
            ndigi = data[0]
            pos = 1 + ndigi * 10
            digis = []
            for j in range(ndigi):
                raw_digi = bytes(data[1 + j * 10:1 + j * 10 + 10])
                digis.append(raw_digi.decode("utf-8", "replace").strip("\x00").strip())
            info = bytes(data[pos:]).decode("utf-8", "replace")
            text = f"{cfrom}>{cto}" + (
                "," + ",".join(d for d in digis if d) if digis else "") + f":{info}"
            try:
                payload = encode_ax25_text(text)
            except Exception:
                payload = bytes(data)

        if payload and self.on_rx_from_client is not None:
            try:
                self.on_rx_from_client(payload)
            except Exception:
                pass

    @staticmethod
    def _baud_code(baud: int) -> int:
        # AGWPE baud codes: 2=300, 3=1200, 4=2400, 5=4800, 6=9600 ...
        # Russian: код скорости в AGWPE.
        codes = {300: 2, 1200: 3, 2400: 4, 4800: 5, 9600: 6,
                 19200: 7, 38400: 8, 57600: 9}
        return codes.get(baud, 3)

    # ------------------------------------------------------------------ RX part
    def _send_frame_to(self, conn, frame_and_payload: bytes):
        try:
            conn.sendall(frame_and_payload)
        except Exception:
            pass

    def broadcast(self, data: bytes):
        """Forward a received radio frame to all clients that enabled monitor.

        ``data`` is the raw AX.25/APRS frame bytes. We parse the AX.25 header,
        build the Dire Wolf style monitor preamble and send a 'U' (unproto)
        frame with the raw info appended.

        Russian:  Передаёт принятый радиокадр клиентам (только с мониторингом).
        English:  Forwards a received radio frame to monitoring clients.
        """
        with self._lock:
            clients = [(c, fl.get("monitor", False)) for c, fl
                       in list(self._client_flags.items())]
        monitors = [c for c, mon in clients if mon]
        a_list = [c for c, mon in clients if not mon]
        del a_list  # clients without monitor enabled get nothing
        if not monitors:
            return

        raw = bytes(data)

        # The radio may deliver either a BINARY AX.25 frame (blob with
        # shifted-ASCII address bytes) or an already-decoded TEXT frame like
        # "SRC>DST,PATH:info". Try text first; only treat as binary AX.25 if
        # the header decodes to readable callsigns AND we can detect it.
        # Russian: радио может отдавать бинарный AX.25 или готовый текст.
        cfrom = ""
        cto = "APRS"
        digis = []
        info = raw
        pid_hex = "F0"

        # 1) try TEXT form "CALL>DST,PATH:info"
        txt = raw.decode("ascii", errors="ignore").strip()
        if ">" in txt and ":" in txt:
            head, _, info_txt = txt.partition(":")
            if ">" in head:
                src_part, dst_part = head.split(">", 1)
                if src_part and dst_part and all(ch.isalnum() or ch in "-_ " for ch in src_part):
                    cfrom = src_part.strip()
                    to_plus = dst_part.split(",")
                    cto = to_plus[0].strip()
                    digis = [d.strip() for d in to_plus[1:] if d.strip()]
                    info = info_txt.encode("ascii", errors="replace")
                    good_as_text = True
                else:
                    good_as_text = False
            else:
                good_as_text = False
        else:
            good_as_text = False

        # 2) otherwise fall back to BINARY AX.25 parsing
        if not good_as_text:
            frame = decode_ax25(raw)
            if frame is not None and frame.source and frame.source.isprintable():
                cfrom = frame.source
                cto = frame.destination
                digis = frame.repeaters
                info = frame.info
                pid_hex = f"{frame.pid:02X}" if frame.pid is not None else "F0"

        # Monitor payload EXACTLY matching the AGWBridge reference server
        # (known to work with UISS and AgwpePort.dll clients):
        #   " 1:Fm SRC To DST Via D1,D2 <UI pid=F0 Len=N >[HH:MM:SS]\r" + info + "\r"
        # Note: Len = len(data) + 1 (info length + the trailing CR), as AGWBridge
        # computes it from the packet text; some clients slice the payload by
        # this Len field, so it must match.
        ts = time.strftime("%H:%M:%S")
        # AGWBridge concat (proven to work with UISS + AgwpePort clients):
        #   " 1:Fm {from} To {to} {via}<UI pid=F0 Len={len+1} >[{HH:MM:SS}]\r"
        #   then the info bytes and a trailing CR. The Len value counts the
        #   info text length plus 1 (trailing CR), exactly like AGWBridge.
        via_seg = "Via " + ",".join(digis) + " " if digis else ""
        info_text = bytes(info).decode("utf-8", "replace")
        info_bytes = info_text.encode("utf-8", "replace")
        info_len = len(info_bytes) + 1  # +1 for trailing CR
        desc = f"<UI pid={pid_hex} Len={info_len} >"
        # One space separates "To {to}" from the via/desc segment.
        preamble = f" 1:Fm {cfrom} To {cto} {via_seg}{desc}[{ts}]\r".encode("ascii", "replace")
        payload = preamble + info_bytes + b"\r"

        hdr = _build_header(0, K_MON_UNPROTO, 0xF0, cfrom, cto, len(payload))
        out = hdr + payload

        if self.on_forward_to_client is not None:
            try:
                self.on_forward_to_client(out)
            except Exception:
                pass
        for c in monitors:
            self._send_frame_to(c, out)

    def _remove_client(self, conn):
        with self._lock:
            was = conn in self._clients
            self._clients.discard(conn)
            self._client_flags.pop(conn, None)
        try:
            conn.close()
        except Exception:
            pass
        if was and self.on_clients_change is not None:
            try:
                self.on_clients_change()
            except Exception:
                pass