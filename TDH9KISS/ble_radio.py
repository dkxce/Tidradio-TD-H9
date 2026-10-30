"""
==============================================================================
  BLE transport for a KISS TNC radio via the bleak library
  Author:  dkxce (c)  https://github.com/dkxce/Tidradio-TD-H9
  Version: v1.1.0.0

  Russian:  BLE-транспорт для работы с рацией как с KISS TNC. Использует
            сервис APRS из приложения Odmaster.
  English:  BLE transport to use a TD-H9 radio as a KISS TNC.

  Designed for the TIDRadio TD-H9 / Odmaster APRS BLE service:
    service  0000af00-0000-1000-8000-00805f9b34fb
    write    0000af01-0000-1000-8000-00805f9b34fb   (TX, KISS data)
    notify   0000af02-0000-1000-8000-00805f9b34fb   (RX, KISS data)

  Bleak runs an asyncio event loop; we bridge it to a Tk callback based model
  using threads and queues so the GUI stays responsive.
==============================================================================
"""

from __future__ import annotations

import asyncio
import threading
from dataclasses import dataclass
from typing import Callable, Optional

from bleak import BleakClient, BleakScanner

import gatt_info

__author__ = "dkxce (c) https://github.com/dkxce/Tidradio-TD-H9"
__version__ = "v1.1.0.0"

# UUIDs used by the Odmaster APRS BLE service
SERVICE_APRS = "0000af00-0000-1000-8000-00805f9b34fb"
CHAR_WRITE = "0000af01-0000-1000-8000-00805f9b34fb"
CHAR_NOTIFY = "0000af02-0000-1000-8000-00805f9b34fb"

import asyncio
import threading
from dataclasses import dataclass
from typing import Callable, Optional

from bleak import BleakClient, BleakScanner

import gatt_info

# UUIDs used by the Odmaster APRS BLE service
SERVICE_APRS = "0000af00-0000-1000-8000-00805f9b34fb"
CHAR_WRITE = "0000af01-0000-1000-8000-00805f9b34fb"
CHAR_NOTIFY = "0000af02-0000-1000-8000-00805f9b34fb"

# Alternative / fallback UUIDs (common 16-bit TID / SPP / TNC assignments)
FALLBACK_WRITE = [
    "0000af01-0000-1000-8000-00805f9b34fb",
    "0000ff02-0000-1000-8000-00805f9b34fb",
    "0000ffe2-0000-1000-8000-00805f9b34fb",
]
FALLBACK_NOTIFY = [
    "0000af02-0000-1000-8000-00805f9b34fb",
    "0000ff01-0000-1000-8000-00805f9b34fb",
    "0000ffe1-0000-1000-8000-00805f9b34fb",
]


@dataclass
class BLEDeviceInfo:
    """Lightweight handle to a discovered BLE device.

    Russian:  Лёгкий идентификатор найденного BLE-устройства.
    """
    address: str
    name: str = ""
    rssi: int = 0

    @property
    def label(self) -> str:
        n = self.name or "<no name>"
        return f"{n} ({self.address})"


class BLEManager:
    """High-level BLE manager bridging asyncio bleak to sync GUI callbacks.

    All public methods are thread-safe and can be called from a Tk callback.
    Asynchronous results (scan list, connection state, incoming data) are
    delivered on callbacks that the GUI installs.
    """

    def __init__(self):
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=self._run_loop, daemon=True, name="ble-loop"
        )
        self._thread.start()

        self.client: Optional[BleakClient] = None
        self.services_loaded = False
        self.current_address: Optional[str] = None
        self.write_char: str = CHAR_WRITE
        self.notify_char: str = CHAR_NOTIFY
        self.service_char_map: dict = {}   # service uuid -> (write, notify) found
        self._writable_props: dict = {}    # char uuid lower -> set of props

        # callbacks
        self.on_scan_result = None    # list[BLEDeviceInfo]
        self.on_connected = None      # (address, name) -> None
        self.on_disconnected = None   # () -> None
        self.on_connect_error = None  # (str) -> None
        self.on_rx = None             # (bytes) -> None, raw KISS/APRS bytes
        self.on_services = None       # (list, write_uuid, notify_uuid) -> None

        self._closing = False
        self._write_lock = threading.Lock()

    # ------------------------------------------------------------------ loop
    def _run_loop(self):
        # Russian: выполняем асинхронный цикл bleak в отдельном потоке.
        # English: run the bleak asyncio loop in a dedicated thread.
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_forever()
        finally:
            self._loop.close()

    def _call(self, cb, *args):
        # Russian: безопасный вызов колбэка без проброса исключений в цикл.
        # English: safely invoke a callback, swallowing exceptions.
        if cb is not None:
            try:
                cb(*args)
            except Exception:
                pass

    def _submit(self, coro):
        # Russian: отправляем корутину в event loop из любого потока.
        # English: submit a coroutine to the event loop from any thread.
        if self._closing or not self._loop.is_running():
            return
        asyncio.run_coroutine_threadsafe(coro, self._loop)

    # ---------------------------------------------------------------- public
    def scan(self, timeout: float = 6.0, callback: Optional[Callable] = None):
        """Start an async scan; results arrive on callback or on_scan_result."""
        if callback is not None:
            self.on_scan_result = callback
        self._submit(self._scan_async(timeout))

    def connect(self, address: str):
        """Connect to a device by its MAC address."""
        self._submit(self._connect_async(address))

    def apply_preset(self, char_records: list):
        """Use previously saved characteristics (from devcfg_<addr>.json).

        ``char_records`` is a list of dicts with keys service/characteristic/
        handle/properties. Sets write_char/notify_char/write_handle/notify_handle
        from the first matching candidates.
        """
        prefer_w = CHAR_WRITE.lower()
        prefer_n = CHAR_NOTIFY.lower()
        w = n = None
        for rec in char_records:
            up = str(rec.get("characteristic", "")).lower()
            props = rec.get("properties", [])
            if w is None and ("write" in props or "write-without-response" in props):
                w = (str(rec["characteristic"]), rec.get("handle"))
                if up == prefer_w:
                    break
        for rec in char_records:
            up = str(rec.get("characteristic", "")).lower()
            props = rec.get("properties", [])
            if n is None and "notify" in props:
                n = (str(rec["characteristic"]), rec.get("handle"))
                if up == prefer_n:
                    break
        if w:
            self.write_char, self.write_handle = w
        if n:
            self.notify_char, self.notify_handle = n
        # seed write props for _write_async before services are re-discovered
        self._writable_props.clear()
        for rec in char_records:
            up = str(rec.get("characteristic", "")).lower()
            props = rec.get("properties", [])
            if "write" in props or "write-without-response" in props:
                self._writable_props[up] = set(props)

    def disconnect(self):
        self._submit(self._disconnect_async())

    def send_raw(self, data: bytes):
        """Write raw bytes (pre-framed) to the BLE write characteristic."""
        self._submit(self._write_async(data))

    def close(self):
        self._closing = True
        if self.client is not None:
            fut = asyncio.run_coroutine_threadsafe(self._disconnect_async(), self._loop)
            try:
                fut.result(timeout=2.0)
            except Exception:
                pass
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout=3.0)

    # ------------------------------------------------------------- internals
    async def _scan_async(self, timeout: float):
        try:
            devices = await BleakScanner.discover(timeout=timeout)
            out = []
            seen = set()
            for dev in devices:
                if dev.address in seen:
                    continue
                seen.add(dev.address)
                out.append(BLEDeviceInfo(address=dev.address, name=dev.name or "",
                                         rssi=self._get_rssi(dev)))
            out.sort(key=lambda d: d.rssi, reverse=True)
            self._call(self.on_scan_result, out)
        except Exception as e:
            self._call(self.on_connect_error, f"Scan failed: {e}")

    @staticmethod
    def _get_rssi(dev) -> int:
        """Best-effort RSSI in bleak 3.x (it lives in ``details``)."""
        try:
            rssi = getattr(dev, "rssi", None)
            if rssi is None:
                rssi = getattr(dev.details, "rssi", None)
            if rssi is None and isinstance(dev.details, dict):
                rssi = dev.details.get("rssi")
            return int(rssi) if rssi is not None else 0
        except Exception:
            return 0

    async def _connect_async(self, address: str):
        self.current_address = address
        self.client = BleakClient(address, disconnected_callback=self._on_bt_disconnect)
        try:
            await self.client.connect(timeout=15.0)
            await self._load_aprs_service()
            name = getattr(self.client, "name", None) or address
            self._call(self.on_connected, address, name)
            # register notify on the resolved characteristic (use handle when
            # the UUID is duplicated across services)
            target_n = self.notify_handle if self.notify_handle is not None else self.notify_char
            try:
                await self.client.start_notify(target_n, self._on_notify)
            except Exception as e:
                self._call(self.on_connect_error,
                           "Connected, but notify register failed: %s" % e)
        except Exception as e:
            self._call(self.on_connect_error, f"Connect failed: {e}")

    async def _disconnect_async(self):
        """Stop notify and disconnect the BLE client, it is up to blame to
        emit on_disconnected (via the disconnected_callback trigger)."""
        try:
            if self.client is not None and self.client.is_connected:
                try:
                    target_n = self.notify_handle if self.notify_handle is not None else self.notify_char
                    await self.client.stop_notify(target_n)
                except Exception:
                    pass
                await self.client.disconnect()
        except Exception:
            pass
        self.client = None
        self.services_loaded = False
        self.current_address = None
        self._call(self.on_disconnected)

    async def _load_aprs_service(self):
        try:
            if not self.services_loaded:
                self.services_loaded = True
                self._resolve_chars(self.client.services)
        except Exception as e:
            self._call(self.on_connect_error, f"Services load failed: {e}")

    def _resolve_chars(self, services):
        """Pick the write / notify characteristics for KISS transport.

        Prefers the known Odmaster APRS UUIDs (af01 / af02) but falls back to
        the first characteristics that expose WRITE / NOTIFY, so that other
        TNC firmwares (TD-H9 variants, SPP TNC) also work. Emits a diagnostic
        list of all found services/characteristics through on_services.
        """
        summary = []
        char_records = []
        prefer_svc = SERVICE_APRS.lower()
        prefer_w = CHAR_WRITE.lower()
        prefer_n = CHAR_NOTIFY.lower()
        chosen_w = None       # (uuid, handle) for write
        chosen_n = None       # (uuid, handle) for notify
        other_svc_w = None
        other_svc_n = None
        self._writable_props: dict = {}

        # First pass: collect all candidates, tracking which belong to af00
        for svc in services:
            svcu = str(svc.uuid).lower()
            is_aprs = svcu == prefer_svc
            for ch in svc.characteristics:
                props = ch.properties
                up = str(ch.uuid).lower()
                summary.append(f"{svc.uuid}  {ch.uuid}  {sorted(props)}")
                char_records.append(gatt_info.characteristic_record(
                    str(svc.uuid), str(ch.uuid), ch.handle, sorted(props)))

                if "write" in props or "write-without-response" in props:
                    self._writable_props.setdefault(up, set(props))
                    cand = (str(ch.uuid), ch.handle)
                    if up == prefer_w or up in FALLBACK_WRITE:
                        if is_aprs:
                            if chosen_w is None:
                                chosen_w = cand
                        elif other_svc_w is None:
                            other_svc_w = cand
                    else:
                        if other_svc_w is None:
                            other_svc_w = cand

                if "notify" in props:
                    cand = (str(ch.uuid), ch.handle)
                    if up == prefer_n or up in FALLBACK_NOTIFY:
                        if is_aprs:
                            if chosen_n is None:
                                chosen_n = cand
                        elif other_svc_n is None:
                            other_svc_n = cand
                    else:
                        if other_svc_n is None:
                            other_svc_n = cand

        # Prefer the af00 APRS characteristics; else any write/notify found
        self.write_char, self.write_handle = chosen_w or other_svc_w or (self.write_char, None)
        self.notify_char, self.notify_handle = chosen_n or other_svc_n or (self.notify_char, None)

        # mark the records the app actually uses (write & notify channels)
        used_ids = {f"{self.write_char.lower()}:{self.write_handle}",
                    f"{self.notify_char.lower()}:{self.notify_handle}"}
        for rec in char_records:
            rid = f"{rec['characteristic'].lower()}:{rec.get('handle')}"
            if rid in used_ids:
                rec["used_in_app"] = True

        self.service_char_map = {"write": self.write_char, "notify": self.notify_char}
        if self.on_services is not None:
            try:
                self.on_services(summary, self.write_char, self.write_handle,
                                 self.notify_char, self.notify_handle, char_records)
            except Exception:
                pass

    async def _write_async(self, data: bytes):
        c = self.client
        if c is None or not c.is_connected:
            self._call(self.on_connect_error, "Not connected")
            return
        props = self._writable_props.get(self.write_char.lower(), set())
        # af01 (and similar KISS data channels) are write-without-response only
        if "write-without-response" in props and "write" not in props:
            use_response = False
        else:
            use_response = ("write" in props)
        target = self.write_handle if self.write_handle is not None else self.write_char
        with self._write_lock:
            try:
                await c.write_gatt_char(target, bytearray(data), response=use_response)
            except Exception as e:
                self._call(self.on_connect_error, f"Write failed: {e}")

    # ---------------------------------------------------------------- callbacks
    def _on_notify(self, _sender, data: bytearray):
        self._call(self.on_rx, bytes(data))

    def _on_bt_disconnect(self, _client):
        self.client = None
        self.services_loaded = False
        self._call(self.on_disconnected)