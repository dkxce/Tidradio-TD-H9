"""
==============================================================================
  KISS TNC framing protocol (frame encapsulation/decapsulation)
  Author:  dkxce (c)  https://github.com/dkxce/Tidradio-TD-H9
  Version: v1.1.0.0

  Russian:  Реализация KISS-протокола (упаковка/распаковка кадров TNC).
  English:  KISS protocol implementation (frame build/parse).

  Implements the byte escaping rules of the KISS protocol (used by TNCs over
  serial lines, BLE and TCP). Byte constants follow the AX.25 / KISS spec:
      FEND  0xC0  frame boundary
      FESC  0xDB  escape
      TFEND 0xDC  escaped FEND
      TFESC 0xDD  escaped FESC
==============================================================================
"""

from __future__ import annotations

__author__ = "dkxce (c) https://github.com/dkxce/Tidradio-TD-H9"
__version__ = "v1.1.0.0"

FEND = 0xC0
FESC = 0xDB
TFEND = 0xDC
TFESC = 0xDD

# KISS command types (port 0 used for data and the common control commands)
CMD_DATA = 0x00
CMD_TXDELAY = 0x01
CMD_PERSIST = 0x02
CMD_SLOTTIME = 0x03
CMD_TXTAIL = 0x04
CMD_FULLDUPLEX = 0x05
CMD_SETHARDWARE = 0x06
CMD_RETURN = 0xFF


def kiss_escape(data: bytes) -> bytearray:
    """Escape raw AX.25 data following the KISS rules.

    Russian:  Экранирует сырые данные AX.25 по правилам KISS.
    """
    out = bytearray()
    for b in data:
        if b == FEND:
            out.append(FESC)
            out.append(TFEND)
        elif b == FESC:
            out.append(FESC)
            out.append(TFESC)
        else:
            out.append(b)
    return out


def frame_kiss(ax25_data: bytes, port: int = 0, command: int = CMD_DATA) -> bytes:
    """Build a full KISS frame (with start/end FEND) for transmission.

    ax25_data: the raw AX.25 (or APRS) payload.
    port:      KISS port number.
    command:   KISS command byte (default CMD_DATA = 0x00).

    Russian:  Собирает полный KISS-кадр со стартовым и концевым FEND.
    English:  Builds a complete KISS frame wrapped in FEND delimiters.
    """
    # Command byte packs port (high nibble) and command type (low nibble).
    # Russian: байт команды упаковывает порт (старшая часть) и тип (младшая).
    cmd_byte = ((port & 0x0F) << 4) | (command & 0x0F)
    body = bytes([cmd_byte]) + kiss_escape(ax25_data)
    return bytes([FEND]) + body + bytes([FEND])


def _fend_parser(on_data):
    """Return a stateful incremental KISS frame parser.

    on_data is called for every decapsulated frame body with
    ``(port, command, payload)`` where payload is the de-escaped bytes.
    The returned object has a ``feed(chunk)`` method that must be called as
    bytes arrive. It correctly handles FESC escapes that are split across
    successive feed() calls (as happens on live TCP streams).

    Russian:  Возвращает инкрементальный парсер KISS-кадров, устойчивый
              к разрыву escape-последовательностей между TCP-порциями.
    English:  Returns a stateful incremental KISS parser safe for streaming.
    """

    class _FendParser:
        def __init__(self, callback):
            self._cb = callback
            self._in_frame = False   # whether a frame is being accumulated
            self._buf = bytearray()  # current frame body (de-escaped)
            self._pending_escape = False  # a FESC is awaiting its TFEND/TFESC

        def feed(self, data: bytes):
            for b in data:
                if self._pending_escape:
                    # Previous byte was FESC; decode the escaped value.
                    # Russian: предыдущий байт был FESC; раскодируем экранированное значение.
                    self._pending_escape = False
                    if b == TFEND:
                        self._buf.append(FEND)
                    elif b == TFESC:
                        self._buf.append(FESC)
                    # A FESC followed by anything else is simply dropped
                    # (malformed stream); we discard both bytes.
                    continue
                if not self._in_frame:
                    if b == FEND:
                        self._in_frame = True
                        self._buf = bytearray()
                    continue
                if b == FEND:
                    # End of frame -> dispatch the decapsulated body.
                    # Russian: конец кадра -> выдаём декодированное тело.
                    if self._buf:
                        try:
                            cmd_byte = self._buf[0]
                            payload = bytes(self._buf[1:])
                            port = (cmd_byte >> 4) & 0x0F
                            command = cmd_byte & 0x0F
                            self._cb(port, command, payload)
                        except Exception:
                            pass
                    self._in_frame = False
                    self._buf = bytearray()
                elif b == FESC:
                    self._pending_escape = True
                else:
                    self._buf.append(b)

    return _FendParser(on_data)


class KISSParser:
    """Callback-based stateful KISS stream parser.

    Usage::
        p = KISSParser(on_frame=lambda port, cmd, payload: ...)
        p.feed(some_bytes)

    on_frame receives (port, command, payload_bytes).

    Russian:  Разбор входящего потока байт на KISS-фреймы с вызовом колбэка.
    English:  Splits an incoming byte stream into KISS frames via a callback.
    """

    def __init__(self, on_frame=None):
        self._parser = _fend_parser(on_frame or (lambda p, c, d: None))

    def feed(self, data: bytes):
        # Forward new bytes to the incremental parser.
        # Russian: передаём новые байты инкрементальному парсеру.
        if not data:
            return
        self._parser.feed(bytes(data))