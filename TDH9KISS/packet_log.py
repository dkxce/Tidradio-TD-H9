"""
==============================================================================
  Packet TX/RX logging to JSON files
  Author:  dkxce (c)  https://github.com/dkxce/Tidradio-TD-H9
  Version: v1.1.0.0

  Russian:  Логирование отправки/приёма пакетов в JSON-файлы.
  English:  Packet TX/RX logging to JSON files.

  Every sent / received APRS packet is appended to a per-device, per-day JSON
  file under ``./log/``. Filename pattern:
      tx_<address>_<yyyyMMdd>.json
      rx_<address>_<yyyyMMdd>.json
  Format: a JSON array of records ``{"address", "frame", "name", "dt"}``.
  A new file is started automatically each calendar day.
==============================================================================
"""

from __future__ import annotations

import datetime
import json
import os
import threading

import paths

__author__ = "dkxce (c) https://github.com/dkxce/Tidradio-TD-H9"
__version__ = "v1.1.0.0"

LOG_DIR = paths.log_dir()

# Guard concurrent appends from BLE/UI threads.
# Russian: защита конкурентных записей из потоков BLE/UI.
_lock = threading.Lock()


def _ensure_dir():
    # Russian: создаёт папку логов при необходимости.
    # English: ensures the log directory exists.
    os.makedirs(LOG_DIR, exist_ok=True)


def _safe_addr(address: str) -> str:
    # Keep only filename-safe characters.
    # Russian: оставляем только безопасные для имени файла символы.
    return "".join(c for c in (address or "") if c.isalnum() or c in "-_.")


def _daily_file(address: str, prefix: str) -> str:
    """Return the log file path for today: <prefix>_<addr>_<yyyyMMdd>.json.

    Russian:  Возвращает путь к файлу лога за сегодня.
    English:  Returns today's log file path.
    """
    date = datetime.datetime.now().strftime("%Y%m%d")
    return os.path.join(LOG_DIR, f"{prefix}_{_safe_addr(address)}_{date}.json")


def log_packet(address: str, frame: str, prefix: str, name: str = ""):
    """Append one packet record to the appropriate daily file.

    prefix is ``tx`` or ``rx``. ``name`` is the device name (optional).

    Russian:  Добавляет запись об одном пакете в дневной файл лога.
    English:  Appends one packet record to the daily log file.
    """
    if not address:
        return
    _ensure_dir()
    path = _daily_file(address, prefix)
    record = {
        "address": address,
        "frame": frame,
        "name": name or "",
        "dt": datetime.datetime.now().isoformat(timespec="seconds"),
    }
    # Load existing entries, append, write back (single-thread safe).
    # Russian: загружаем существующие записи, добавляем и сохраняем (потокобезопасно).
    with _lock:
        entries = []
        if os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, list):
                    entries = data
            except Exception:
                entries = []
        entries.append(record)
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(entries, f, ensure_ascii=False, indent=2)
        except Exception:
            pass


def log_tx(address: str, frame: str, name: str = ""):
    # Russian: лог передачи (TX).
    # English: log a transmitted packet.
    log_packet(address, frame, "tx", name)


def log_rx(address: str, frame: str, name: str = ""):
    # Russian: лог приёма (RX).
    # English: log a received packet.
    log_packet(address, frame, "rx", name)