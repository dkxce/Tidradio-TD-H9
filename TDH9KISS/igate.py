"""
==============================================================================
  IGate bridge: radio APRS <-> APRS-IS network
  Author:  dkxce (c)  https://github.com/dkxce/Tidradio-TD-H9
  Version: v1.1.0.0

  Russian:  Самостоятельный блок IGate между радиоэфиром APRS и сетью
            APRS-IS. Слушает рацию и передаёт пакеты в APRS-IS и наоборот.
  English:  Standalone IGate bridging the radio APRS feed and the APRS-IS
            network.

  Data flow (TCP as an APRS-IS client):
      Network -> Radio (a): a packet is forwarded to the radio only if it
          came with the IGate callsign <IGATE_NAME> in the path, does NOT
          contain qAR nor qAO constructs, and (optionally, depending on the
          check_tcpip flag) contains TCPIP.
      Radio -> Network (b): every packet received from the air is sent to
          APRS-IS with the path suffix ",qAR,<IGATE_NAME>".

  Client login:
      user <APRSIS_CLIENT> pass <passcode> vers TDH9KissIGate v1.0 filter <filter>
  Default filter:  filter d/<IGATE_NAME>*
==============================================================================
"""

from __future__ import annotations

import json
import socket
import threading
import time
from typing import Callable, Optional

from aprsis_server import compute_passcode
import paths

__author__ = "dkxce (c) https://github.com/dkxce/Tidradio-TD-H9"
__version__ = "v1.1.0.0"

CLIENT_APP = "TDH9KissIGate v1.0"

# Path to the IGate settings file (stable, PyInstaller-aware).
# Russian: путь к файлу настроек IGate (устойчив к PyInstaller).
SETTINGS_FILE = paths.settings_path()

# Default settings (overridden from settings.json)
DEFAULT_SETTINGS = {
    "aprsis_client": "NOCALL-10",  # callsign used to connect (APRSIS_CLIENT)
    "igate_name": "NOCALL-1",      # IGate callsign shown to the network (IGATE_NAME)
    "passcode": 0,                 # APRS-IS passcode for the client callsign
    "server": "rotate.aprs2.net",  # remote APRS-IS server
    "port": 14580,                 # remote APRS-IS port
    "filter": "",                  # APRS-IS filter; default = "d/<IGATE_NAME>*"
    # behaviour toggles
    "check_tcpip": True,   # require TCPIP present in path to gate to radio
    "check_no_qar": True,  # require absence of qAR in path to gate to radio
    "check_no_qao": True,  # require absence of qAO in path to gate to radio
    "enabled": False,      # master switch for the IGate
}


def load_settings() -> dict:
    """Load IGate settings from settings.json, else return defaults.

    Russian:  Загружает настройки IGate из settings.json.
    English:  Loads IGate settings from settings.json.
    """
    cfg = dict(DEFAULT_SETTINGS)
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            cfg.update(data)
    except Exception:
        pass
    return cfg


def save_settings(cfg: dict) -> bool:
    """Persist IGate settings to settings.json.

    Russian:  Сохраняет настройки IGate в settings.json.
    English:  Saves IGate settings to settings.json.
    """
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


def _split_header(frame: str):
    """Split 'SRC>DST,PATH:info' into (head, info).

    Returns (head_up, info) where head_up is the raw header with the ':' cut.
    """
    if ":" in frame:
        head, _, info = frame.partition(":")
        return head, info
    return frame, ""


def parse_packet_parts(frame: str):
    """Parse a text APRS frame into (source, dest, path_list, info).

    path_list are the digipeater/q-constructs after the destination callsign.
    """
    head, info = _split_header(frame)
    src = ""
    rest = ""
    if ">" in head:
        src, _, rest = head.partition(">")
    dst = ""
    path = []
    if rest:
        pieces = rest.split(",")
        dst = pieces[0]
        path = [p for p in pieces[1:] if p]
    return src.strip(), dst.strip(), path, info


class IGate:
    """APRS-IS client that bridges the radio feed and the network.

    Russian:  APRS-IS клиент, соединяющий радиоэфир с сетью.
    English:  APRS-IS client bridging the radio feed and the network.
    """

    def __init__(
        self,
        settings: Optional[dict] = None,
        on_rx_to_radio: Optional[Callable[[bytes], None]] = None,
        on_log: Optional[Callable[[str], None]] = None,
        settings_getter: Optional[Callable[[], dict]] = None,
    ):
        # settings copy so defaults apply
        cfg = dict(DEFAULT_SETTINGS)
        if settings:
            cfg.update(settings)
        self.cfg = cfg

        # Optional live getter: called on every packet to read current
        # settings/flags from the GUI, so toggling them needs no restart.
        # Russian: живой получатель настроек — вызывается на каждый пакет,
        # чтобы включение/выключение флагов применялось без перезапуска.
        self.settings_getter = settings_getter

        # Called with a decoded APRS frame (bytes) to transmit over the radio.
        self.on_rx_to_radio = on_rx_to_radio
        # Called for UI logging (str).
        self.on_log = on_log

        self._sock: Optional[socket.socket] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._connected = False
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ logging
    def _log(self, msg: str):
        if self.on_log is not None:
            try:
                self.on_log(msg)
            except Exception:
                pass

    # ---------------------------------------------------------------- lifecycle
    def start(self):
        # Russian: запуск фонового цикла подключения к APRS-IS.
        # English: starts the background connect/read loop.
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        # Russian: остановка IGate и закрытие сокета.
        # English: stops the IGate and closes the socket.
        self._running = False
        with self._lock:
            if self._sock is not None:
                try:
                    self._sock.close()
                except Exception:
                    pass
                self._sock = None
        if self._thread is not None:
            self._thread.join(timeout=3.0)
            self._thread = None
        self._connected = False

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def enabled(self) -> bool:
        return bool(self.cfg.get("enabled", False))

    # ---------------------------------------------------------------- main loop
    def _run(self):
        while self._running:
            if not self.enabled:
                time.sleep(1.0)
                continue
            try:
                self._connect_and_loop()
            except Exception as e:
                self._log(f"[IGate] error: {e}")
                time.sleep(5.0)

    def _connect_and_loop(self):
        """Connect to APRS-IS, log in, and process lines until disconnected."""
        cfg = self.cfg
        server = cfg.get("server", DEFAULT_SETTINGS["server"])
        port = int(cfg.get("port", DEFAULT_SETTINGS["port"]))
        client = cfg.get("aprsis_client", "")
        igate_name = cfg.get("igate_name", "")
        passcode = int(cfg.get("passcode", 0) or 0)
        user_filter = cfg.get("filter", "") or f"d/{(igate_name or '').split('-', 1)[0]}*"

        # If passcode was left 0/empty, compute it from the client callsign.
        if not passcode:
            passcode = compute_passcode(client)

        self._log(f"[IGate] connecting to {server}:{port} as {client}")

        sock = socket.create_connection((server, port), timeout=15.0)
        sock.settimeout(60.0)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        with self._lock:
            self._sock = sock
        self._connected = True

        # Build and send the login line first; banner lines are read and
        # ignored in the main loop below (prevents a deadlock where the
        # server waits for login while we wait for a banner).
        # Russian: логин шлём сразу; баннер читаем в основном цикле.
        login = (f"user {client} pass {passcode} vers {CLIENT_APP} "
                 f"filter {user_filter}\r\n")
        self._log(f"[IGate] login: user {client} pass {passcode} vers {CLIENT_APP} filter {user_filter}")
        sock.sendall(login.encode("utf-8"))

        buf = b""
        try:
            while self._running and self.enabled:
                try:
                    data = sock.recv(4096)
                except socket.timeout:
                    # keepalive ping so the server does not drop us
                    try:
                        sock.sendall(b"# ping\r\n")
                    except Exception:
                        break
                    continue
                if not data:
                    break
                buf += data
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    line = line.rstrip(b"\r")
                    if line:
                        self._process_server_line(line)
        except socket.error:
            pass
        finally:
            self._log("[IGate] disconnected")
            try:
                sock.close()
            except Exception:
                pass
            with self._lock:
                self._sock = None
            self._connected = False

    # ------------------------------------------------------------- network RX
    def _process_server_line(self, line: bytes):
        # Russian: обработка одной строки от сервера APRS-IS.
        text = line.decode("utf-8", errors="replace").strip()
        if not text:
            return
        if text.startswith("#") or text.lower().startswith("user ") \
                or text.lower().startswith("ping"):
            # comment / status / login-echo -> ignore
            # Russian: комментарии/статус/эхо логина не логируем как трафик.
            return
        # It is a packet -> decide whether to gate it to the radio.
        if self._should_gate_to_radio(text):
            self._log(f"[IGate net -> radio] {text}")
            if self.on_rx_to_radio is not None:
                try:
                    self.on_rx_to_radio(text.encode("utf-8"))
                except Exception:
                    pass
        else:
            self._log(f"[IGate net --skip-> radio] {text}")

    def _live_cfg(self) -> dict:
        """Return current settings, merging any live getter output.

        Russian:  Возвращает актуальные настройки, объединяя вывод getter'а.
        """
        if self.settings_getter is not None:
            try:
                live = self.settings_getter()
                if isinstance(live, dict):
                    cfg = dict(self.cfg)
                    cfg.update(live)
                    return cfg
            except Exception:
                pass
        return self.cfg

    def _should_gate_to_radio(self, frame: str) -> bool:
        """Apply rule (a): decide whether to send this network packet to radio.

        Russian:  Применяет правило (a): стоит ли слать сетевой пакет в радио.
        """
        cfg = self._live_cfg()
        igate_name = cfg.get("igate_name", "").upper()
        check_tcpip = cfg.get("check_tcpip", True)
        check_no_qar = cfg.get("check_no_qar", True)
        check_no_qao = cfg.get("check_no_qao", True)

        src, dst, path, info = parse_packet_parts(frame)
        path_upper = ",".join(path).upper()

        # require the igate name present in the path
        if igate_name and igate_name not in path_upper:
            return False

        # optional: require TCPIP present
        if check_tcpip and "TCPIP" not in path_upper:
            return False

        # require absence of qAR / qAO if those flags are on
        if check_no_qar and "QAR" in path_upper:
            return False
        if check_no_qao and "QAO" in path_upper:
            return False

        return True

    # ------------------------------------------------------------- radio RX
    def radio_rx(self, frame: bytes):
        """Process a frame received from the radio (rule b).

        The decoded APRS text is sent to the network with the path suffix
        ",qAR,<IGATE_NAME>" appended.

        Russian:  Обрабатывает кадр из эфира (rule b): шлёт в сеть с суффиксом
                  ",qAR,<IGATE_NAME>".
        """
        if not self._connected or not self.enabled:
            return
        text = frame.decode("utf-8", errors="replace").strip()
        if not text:
            return
        cfg = self._live_cfg()
        igate_name = cfg.get("igate_name", "")
        # Append ,qAR,<IGATE_NAME> to the path (before the ':' info field).
        out = self._append_to_path(text, f"qAR,{igate_name}")
        self._log(f"[IGate radio -> net] {text}  ->  {out}")
        try:
            with self._lock:
                if self._sock is not None:
                    self._sock.sendall((out + "\r\n").encode("utf-8"))
        except Exception as e:
            self._log(f"[IGate] tx error: {e}")

    @staticmethod
    def _append_to_path(frame: str, suffix: str) -> str:
        """Insert ','+suffix into the destination/path portion of the frame."""
        head, info = _split_header(frame)
        if ">" in head:
            sep = ">"
            left, _, rest = head.partition(">")
            return f"{left}>{rest},{suffix}:{info}" if info else f"{left}>{rest},{suffix}"
        return frame