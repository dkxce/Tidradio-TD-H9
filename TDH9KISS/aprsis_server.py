"""
==============================================================================
  APRS-IS compatible server (bridge radio <-> APRS-IS clients)
  Author:  dkxce (c)  https://github.com/dkxce/Tidradio-TD-H9
  Version: v1.1.0.0

  Russian:  Сервер, совместимый с протоколом APRS-IS (порт по умолчанию
            14580). Слушает эфир и рассылает принятые пакеты всем
            авторизованным клиентам, а пакеты от клиентов передаёт в эфир.
            Обязательна проверка passcode по алгоритму APRS-IS. Фильтры не
            используются (клиенты получают весь эфир).
  English:  APRS-IS compatible server. Bridges received radio frames to all
            authorized clients and forwards client transmissions to the radio.
            Passcode verification is mandatory; no filters are applied.

  Login format (APRS-IS):
      user CALLSIGN pass PASSCODE vers PROGRAM 1.0 filter FILTER
  Server replies:
      # logresp CALLSIGN verified, server SID
      # logresp CALLSIGN unverified, server SID

  Passcode algorithm:
      hash each char of the uppercased callsign (excluding SSID): code =
      ((code << 8) | ascii) ... then a XOR/mask dance producing a 5-digit
      number. Standard APRS-IS implementation.

  Data flow:
      Client -> server (non-login line like "CALL>DST:info") -> on_rx_to_radio
      Radio  -> server (decoded "CALL>DST:info") -> sent to every client
==============================================================================
"""

from __future__ import annotations

import socket
import threading
from typing import Callable, Optional

from ax25 import to_aprs_text

__author__ = "dkxce (c) https://github.com/dkxce/Tidradio-TD-H9"
__version__ = "v1.1.0.0"

SERVER_ID = "TIDRADIO-TD-H9"  # SID advertised in login responses


def compute_passcode(callsign: str) -> int:
    """Compute the canonical APRS-IS passcode for a callsign.

    Standard APRS-IS algorithm (reference: aprslib):

        callsign = callsign.split('-')[0].upper()
        code = 0x73E2
        for i, char in enumerate(callsign):
            code ^= ord(char) << (8 if i % 2 == 0 else 0)
        return code & 0x7FFF

    The shift alternates by index parity: even-position chars shift by 8,
    odd-position chars XOR in place (shift 0). SSID is stripped. Result is a
    15-bit integer.

    Russian:  Вычисляет канонический passcode APRS-IS для позывного.
    English:  Computes the canonical APRS-IS passcode for a callsign.
    """
    call = (callsign or "").split("-", 1)[0].upper()
    call = "".join(ch for ch in call if ch.isalnum())

    code = 0x73E2
    for i, ch in enumerate(call):
        shift = 8 if i % 2 == 0 else 0
        code ^= ord(ch) << shift
    return code & 0x7FFF


# ---------------------------------------------------------------------------

class APRSServer:
    """APRS-IS compatible TCP server.

    Russian:  TCP-сервер с протоколом APRS-IS.
    English:  APRS-IS compatible TCP server.
    """

    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 14580,
        on_rx_from_client: Optional[Callable[[bytes], None]] = None,
        on_forward_to_client: Optional[Callable[[bytes], None]] = None,
        on_clients_change: Optional[Callable[[], None]] = None,
    ):
        self.host = host
        self.port = port
        # Called with the raw AX.25/APRS bytes to transmit to the radio.
        self.on_rx_from_client = on_rx_from_client
        # Called for debug/info with the bytes sent to clients.
        self.on_forward_to_client = on_forward_to_client
        # Called when a client connects or disconnects.
        # Russian: вызывается при подключении/отключении клиента.
        self.on_clients_change = on_clients_change

        self._sock: Optional[socket.socket] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False
        # client socket -> authenticated? and its configured callsign
        self._clients: dict = {}
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

        Each entry: dict(addr, port, callsign, can_tx).
        APRS-IS: unverified clients are read-only (can_tx=False).

        Russian:  Возвращает список клиентов для отображения.
        """
        with self._lock:
            out = []
            for conn, info in list(self._clients.items()):
                try:
                    ra, rp = conn.getpeername()[:2]
                except Exception:
                    ra, rp = "?", 0
                out.append({
                    "addr": ra, "port": rp,
                    "callsign": info.get("callsign", ""),
                    "can_tx": bool(info.get("authenticated", False)),
                })
            return out

    # ----------------------------------------------------------------- internal
    def _accept_loop(self):
        while self._running:
            try:
                conn, _addr = self._sock.accept()
            except Exception:
                break
            with self._lock:
                self._clients[conn] = {"authenticated": False, "callsign": ""}
            if self.on_clients_change is not None:
                try:
                    self.on_clients_change()
                except Exception:
                    pass
            threading.Thread(target=self._handle_client, args=(conn,),
                             daemon=True).start()

    def _handle_client(self, conn: socket.socket):
        # Russian: читает строки APRS-IS от клиента.
        # English: reads APRS-IS lines from the client.
        buf = b""
        try:
            conn.settimeout(60)
            # send greeting / welcome banner (optional, some clients expect it)
            self._send(conn, f"# {SERVER_ID}: connection accepted\r\n".encode("utf-8"))
            while self._running:
                try:
                    data = conn.recv(4096)
                except socket.timeout:
                    continue
                if not data:
                    break
                buf += data
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    line = line.rstrip(b"\r")
                    if line:
                        self._process_line(conn, line)
        except Exception:
            pass
        finally:
            self._remove_client(conn)

    def _process_line(self, conn, line: bytes):
        """Parse one APRS-IS line from a client."""
        if not line:
            return
        text = line.decode("utf-8", errors="replace").strip()
        low = text.lower()

        # application login:  user CALL pass PASS vers ... filter ...
        if low.startswith("user "):
            self._do_login(conn, text)
            return

        # comment / ping / status lines are ignored
        if text.startswith("#") or low.startswith("ping") or low == "periodic":
            return

        # kill / exit closes the session
        if low.startswith("kill") or low.startswith("exit"):
            conn.close()
            return

        # otherwise: an APRS frame to transmit over the radio
        with self._lock:
            auth = self._clients.get(conn, {}).get("authenticated", False)
        if not auth:
            self._send(conn, b"# unverified, login first\r\n")
            return
        if self.on_rx_from_client is not None:
            try:
                self.on_rx_from_client(line)
            except Exception:
                pass

    def _do_login(self, conn, text: str):
        """Handle a 'user CALL pass PASS vers ...' login line."""
        # parse:  user <call> pass <passcode> vers <prog> <ver> [filter ...]
        parts = text.split()
        # ensure there is a pass token
        passcode_raw = ""
        callsign = ""
        for i, p in enumerate(parts):
            if p.lower() == "user" and i + 1 < len(parts):
                callsign = parts[i + 1]
            if p.lower() == "pass" and i + 1 < len(parts):
                passcode_raw = parts[i + 1]

        if not callsign or not passcode_raw:
            self._send(conn, b"# logresp none unverified\r\n")
            return

        # verify the provided passcode against the computed one
        try:
            provided = int(passcode_raw)
        except ValueError:
            provided = -1
        expected = compute_passcode(callsign)
        ok = (provided == expected)

        with self._lock:
            self._clients[conn]["authenticated"] = ok
            # keep the callsign even for unverified clients so the UI can
            # show who is connected (read-only). / сохраняем позывной даже
            # для неавторизованных, чтобы в UI было видно подключённого.
            self._clients[conn]["callsign"] = callsign

        if ok:
            self._send(conn,
                       f"# logresp {callsign} verified, server {SERVER_ID}\r\n".encode("utf-8"))
            self._on_raw_tx_to_radio(f"{callsign}>APRS:{SERVER_ID} online".encode("utf-8"))
        else:
            self._send(conn,
                       f"# logresp {callsign} unverified, server {SERVER_ID}\r\n".encode("utf-8"))

    # ------------------------------------------------------------------- helpers
    def _send(self, conn, data: bytes):
        try:
            conn.sendall(data)
        except Exception:
            pass

    def _remove_client(self, conn):
        with self._lock:
            was = conn in self._clients
            self._clients.pop(conn, None)
        try:
            conn.close()
        except Exception:
            pass
        if was and self.on_clients_change is not None:
            try:
                self.on_clients_change()
            except Exception:
                pass

    def _on_raw_tx_to_radio(self, data: bytes):
        # Helper: forward a raw APRS text to the radio callback (used on login).
        if self.on_rx_from_client is not None:
            try:
                self.on_rx_from_client(data)
            except Exception:
                pass

    # ----------------------------------------------------------------- public API
    def broadcast(self, data: bytes):
        """Forward a received radio frame to every authenticated client.

        ``data`` is the raw AX.25/APRS payload; it is sent as a UTF-8 line.

        Russian:  Передаёт принятый радиокадр всем клиентам (включая неавторизованных,
                  которым разрешено только чтение эфира).
        English:  Forwards a received radio frame to all clients (including
                  unverified ones, who are allowed read-only access to the feed).
        """
        with self._lock:
            clients = list(self._clients.keys())
        if not clients:
            return
        raw = bytes(data)
        # The radio usually delivers a BINARY AX.25 frame; decode it into a
        # readable 'SRC>DST,..:info' string before sending to clients.
        # Russian: радио отдаёт бинарный AX.25 — декодируем в читаемый текст APRS.
        txt = to_aprs_text(raw)
        if not txt or not txt.strip():
            return
        payload = txt.strip().encode("utf-8") + b"\r\n"

        if self.on_forward_to_client is not None:
            try:
                self.on_forward_to_client(payload)
            except Exception:
                pass
        for c in clients:
            self._send(c, payload)