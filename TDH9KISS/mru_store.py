"""
==============================================================================
  Small MRU (most-recently-used) JSON storage helpers
  Author:  dkxce (c)  https://github.com/dkxce/Tidradio-TD-H9
  Version: v1.1.0.0

  Russian:  Небольшие помощники хранения истории (MRU) в JSON-файлах.
  English:  Small MRU JSON storage helpers.

  Writes and reads simple ordered lists of records to JSON files under
  ``./data/``. The newest record is always first in the list.
==============================================================================
"""

from __future__ import annotations

import datetime
import json
import os

import paths

__author__ = "dkxce (c) https://github.com/dkxce/Tidradio-TD-H9"
__version__ = "v1.1.0.0"

DATA_DIR = paths.data_dir()

CONNECTED_DEVICES = "connected_devices_mru.json"
SENT_MESSAGES = "sent_messages.json"

MAX_ENTRIES = 16


def _ensure_dir():
    # Russian: создаёт папку данных при необходимости.
    # English: ensures the data directory exists.
    os.makedirs(DATA_DIR, exist_ok=True)


def _path(name: str) -> str:
    return os.path.join(DATA_DIR, name)


def _read_list(name: str) -> list:
    """Read a JSON-list file, tolerating missing/corrupt files.

    Russian:  Читает JSON-список, устойчиво к отсутствию файла.
    English:  Reads a JSON list file, tolerant to missing/corrupt data.
    """
    _ensure_dir()
    p = _path(name)
    if not os.path.isfile(p):
        return []
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
    except Exception:
        pass
    return []


def _write_list(name: str, data: list):
    """Atomically write a JSON-list file.

    Russian:  Записывает JSON-список в файл.
    English:  Writes a JSON list to a file.
    """
    _ensure_dir()
    p = _path(name)
    try:
        with open(p, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def now_str() -> str:
    """Returns a local datetime string like '2026-10-30 15:04:05'."""
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ------------------------------------------------------------------ devices


def load_connected_devices() -> list:
    """Return list of dicts: {name, address, last_seen} (newest first)."""
    return _read_list(CONNECTED_DEVICES)


def record_connected_device(name: str, address: str):
    """Add/update a connected device record and persist it."""
    items = load_connected_devices()
    items = [it for it in items if it.get("address") != address]
    items.insert(0, {"name": name or "", "address": address, "last_seen": now_str()})
    _write_list(CONNECTED_DEVICES, items[:MAX_ENTRIES])


# ----------------------------------------------------------------- goals: sent messages


def load_sent_messages() -> list:
    """Return list of dicts: {frame, dt, address, name} (newest first)."""
    return _read_list(SENT_MESSAGES)


def record_sent_message(frame: str, address: str = "", name: str = ""):
    """Record a sent APRS frame (text) to which device, and persist it."""
    items = load_sent_messages()
    items = [it for it in items if it.get("frame") != frame]
    items.insert(0, {"frame": frame, "dt": now_str(),
                     "address": address or "", "name": name or ""})
    _write_list(SENT_MESSAGES, items[:MAX_ENTRIES])


# ------------------------------------------------------------------- device config


def load_device_config(address: str) -> dict:
    """Load per-device characteristics config, or return {}."""
    safe = _sanitize_address(address)
    return _read_list(safe)  # returns list of char records


def save_device_config(address: str, char_records: list):
    """Save per-device characteristics list to devcfg_<addr>.json."""
    safe = _sanitize_address(address)
    fname = f"devcfg_{safe}.json"
    _write_list(fname, char_records)


def _sanitize_address(address: str) -> str:
    return "".join(c for c in (address or "") if c.isalnum() or c in "-_.")