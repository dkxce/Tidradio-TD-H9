"""
==============================================================================
  KISS TNC over TCP/IP server
  Author:  dkxce (c)  https://github.com/dkxce/Tidradio-TD-H9
  Version: v1.1.0.0

  Russian:  KISS TNC поверх TCP/IP — сервер, к которому подключаются внешние
            APRS-приложения. Клиент шлёт/получает сырые KISS-кадры
            (0xC0 CMD ... 0xC0), как последовательный TNC по сети.
  English:  KISS TNC over TCP/IP server. The client sends/receives raw
            KISS frames, exactly like a serial TNC presented over TCP.

  Incoming radio frames are wrapped into KISS frames and forwarded to every
  connected client.
==============================================================================
"""

from __future__ import annotations

import socket
import threading
from typing import Callable, Optional

from kiss import KISSParser, frame_kiss

__author__ = "dkxce (c) https://github.com/dkxce/Tidradio-TD-H9"
__version__ = "v1.1.0.0"


def _peek_kiss(data: bytes) -> bool:
    """Heuristic: does this look like a raw KISS frame (starts with FEND)?

    Russian:  Эвристика: похоже ли это на сырой KISS-кадр (начинается с FEND).
    English:  Heuristic: does the data look like a raw KISS frame.
    """
    d = data.lstrip()
    return len(d) >= 2 and d[0] in (0xC0, 0xDB)  # FEND or FESC


class KISS_TCPServer:
    """TCP server exposing the radio as a KISS TNC (binary framing).

    Russian:  TCP-сервер, предоставляющий радио как KISS TNC (бинарный режим).
    English:  TCP server exposing the radio as a KISS TNC (binary framing).
    """

    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 8023,
        on_rx_from_client: Optional[Callable[[bytes], None]] = None,
        on_forward_to_client: Optional[Callable[[bytes], None]] = None,
        on_clients_change: Optional[Callable[[], None]] = None,
        binary_mode: bool = True,
    ):
        self.host = host
        self.port = port
        # Called with the raw AX.25/APRS bytes to transmit to the radio.
        self.on_rx_from_client = on_rx_from_client
        # Called for debug/info with the frame bytes forwarded to clients.
        self.on_forward_to_client = on_forward_to_client
        # Called when a client connects or disconnects.
        # Russian: вызывается при подключении/отключении клиента.
        self.on_clients_change = on_clients_change
        # Kept for compatibility; the server always runs binary KISS framing.
        self.binary_mode = binary_mode

        self._sock: Optional[socket.socket] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._clients: set = set()
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
        self._sock.listen(5)
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

        KISS clients have no auth/login; all are full TX clients, so
        can_tx=True and callsign is unknown ('').

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
            if self.on_clients_change is not None:
                try:
                    self.on_clients_change()
                except Exception:
                    pass
            threading.Thread(target=self._handle_client, args=(conn,),
                             daemon=True).start()

    def _handle_client(self, conn: socket.socket):
        # Each connection runs its own KISS reader thread.
        # Russian: для каждого соединения свой поток чтения KISS.
        self._handle_binary(conn)
        self._remove_client(conn)

    def _handle_binary(self, conn: socket.socket):
        """Binary KISS mode: forward raw frames to the radio; echo radio
        frames to the client as raw KISS bytes.

        Russian:  Бинарный KISS-режим: сырые кадры уходят в радио, пакеты из
                  радио возвращаются клиенту как сырые KISS-байты.
        English:  Binary KISS mode for raw framing.
        """
        parser = KISSParser(on_frame=self._on_client_frame)
        try:
            conn.settimeout(60)
            while self._running:
                try:
                    data = conn.recv(4096)
                except socket.timeout:
                    continue
                if not data:
                    break
                parser.feed(data)
        except Exception:
            pass

    def _on_client_frame(self, port, command, payload):
        """A complete KISS data frame was received from a TCP client."""
        if payload and command == 0x00:  # CMD_DATA
            if self.on_rx_from_client is not None:
                try:
                    self.on_rx_from_client(payload)
                except Exception:
                    pass

    def _send(self, conn, data: bytes):
        try:
            conn.sendall(data)
        except Exception:
            pass

    def _remove_client(self, conn):
        with self._lock:
            was = conn in self._clients
            self._clients.discard(conn)
        try:
            conn.close()
        except Exception:
            pass
        if was and self.on_clients_change is not None:
            try:
                self.on_clients_change()
            except Exception:
                pass

    # ----------------------------------------------------------------- public API
    def broadcast(self, data: bytes):
        """Forward a received radio frame to all connected clients.

        ``data`` (raw AX.25/APRS) is wrapped into a KISS frame and sent raw.

        Russian:  Передаёт полученный радиокадр всем подключённым клиентам.
        English:  Forwards a received radio frame to all connected clients.
        """
        with self._lock:
            clients = list(self._clients)
        if not clients:
            return
        # wrap raw AX.25 payload into a KISS frame (CMD_DATA on port 0)
        payload = frame_kiss(bytes(data))
        if self.on_forward_to_client is not None:
            try:
                self.on_forward_to_client(payload)
            except Exception:
                pass
        for c in clients:
            self._send(c, payload)