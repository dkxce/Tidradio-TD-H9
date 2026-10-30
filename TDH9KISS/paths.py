"""
==============================================================================
  Application data-path helper (works with PyInstaller)
  Author:  dkxce (c)  https://github.com/dkxce/Tidradio-TD-H9
  Version: v1.1.0.0

  Russian:  Вспомогательный модуль определения папок данных. В исходном
            запуске (python main.py) папки расположены рядом с модулями.
            В собранном EXE (PyInstaller) `__file__` указывает во временную
            распаковочную папку `_MEIxxxx`, которая исчезает при выходе, —
            поэтому настройки/история/логи кладутся рядом с самим EXE и
            сохраняются между запусками.
  English:  Helper that resolves data directories. In source mode the folders
            live next to the modules. In a PyInstaller EXE, `__file__` points
            into the temporary `_MEIxxxx` extraction dir, so config / MRU /
            logs are stored next to the executable to persist across runs.
==============================================================================
"""

from __future__ import annotations

import os
import sys

__author__ = "dkxce (c) https://github.com/dkxce/Tidradio-TD-H9"
__version__ = "v1.1.0.0"


def is_frozen() -> bool:
    """True when running inside a bundled (PyInstaller) executable.

    Russian:  Возвращает True, если приложение запущено как собранный EXE.
    """
    return bool(getattr(sys, "frozen", False))


def base_dir() -> str:
    """Root folder for all writable data: next to the EXE or next to modules.

    Russian:  Корневая папка для всех записываемых данных.
    English:  Root folder for all writable data.
    """
    if is_frozen():
        # onefile: sys.executable is the exe path (stable, not _MEI)
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def data_dir() -> str:
    """Writable folder for MRU/history data (./data).

    Russian:  Папка истории/MRU.
    """
    return os.path.join(base_dir(), "data")


def log_dir() -> str:
    """Writable folder for packet logs (./log).

    Russian:  Папка журналов пакетов.
    """
    return os.path.join(base_dir(), "log")


def settings_path() -> str:
    """Path to the IGate settings.json.

    Russian:  Путь к файлу настроек IGate.
    """
    return os.path.join(base_dir(), "settings.json")