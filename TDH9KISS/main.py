"""
==============================================================================
  KISS TNC over BLE  —  GUI app for a TIDRadio TD-H9 APRS radio
  Author:  dkxce (c)  https://github.com/dkxce/Tidradio-TD-H9
  Version: v1.1.0.0

  Russian:  Графическое приложение (tkinter) для работы с рацией TD-H9 как
            с KISS TNC через Bluetooth LE: скан устройств, подключение,
            приём/передача APRS, сервер KISS TNC over TCP/IP.
  English:  Tkinter app that turns a TD-H9 radio into a KISS TNC over BLE:
            device scan, connect, APRS RX/TX and a KISS-over-TCP server.

  Features:
    * Scan and pick a BLE device.
    * Connect to the APRS service and exchange KISS frames (write 0xaf01,
      notify 0xaf02).
    * Show decoded incoming APRS packets in a Tk window.
    * Send APRS packets (KISS-framed) from the window.
    * Run a KISS TNC over TCP/IP server so external APRS apps can use the radio.

  Run:  python main.py
  Requires:  pip install bleak
==============================================================================
"""

from __future__ import annotations

import datetime
import queue
import threading
import tkinter as tk
from tkinter import messagebox, ttk

from ble_radio import BLEManager
from kiss import KISSParser, frame_kiss
from kiss_tcp_server import KISS_TCPServer
from agw_server import AGW_TCPServer
from aprsis_server import APRSServer
from aprs_parser import parse_aprs
from ax25 import to_aprs_text, encode_ax25_text
from igate import IGate, load_settings, save_settings
import mru_store
import packet_log

__author__ = "dkxce (c) https://github.com/dkxce/Tidradio-TD-H9"
__version__ = "v1.1.0.0"


class App:
    """Main application window. / Главное окно приложения."""
    # Russian: главное окно приложения.
    # English: main application window.

    # ------------------------------------------------------------------ init
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title("TIDRadio TD-H9 · APRS KISS TNC BLE by dkxce")
        root.geometry("780x680")
        root.protocol("WM_DELETE_WINDOW", self._close)

        self.ble = BLEManager()
        self.parser = KISSParser(on_frame=self._on_kiss_frame)
        self.server = KISS_TCPServer(
            port=8023,
            on_rx_from_client=self._client_tx,
            on_forward_to_client=self._log_server_tx,
            on_clients_change=self._on_clients_changed,
        )
        self.agw_server = AGW_TCPServer(
            port=8000,
            on_rx_from_client=self._client_tx,
            on_forward_to_client=self._log_server_tx,
            on_clients_change=self._on_clients_changed,
            station_callsign="TNC1",
        )
        self.aprsis_server = APRSServer(
            port=14580,
            on_rx_from_client=self._client_tx_aprs,
            on_forward_to_client=self._log_server_tx,
            on_clients_change=self._on_clients_changed,
        )
        # Debug: dump every inbound AGW frame from the client into the log.
        # Russian: отладка — выводим каждый входящий AGW-кадр клиента в лог.
        self.agw_server._debug_cb = self._agw_debug_frame

        # Thread-safe UI updates: cross-thread callbacks push into this queue.
        # Russian: потокобезопасная очередь обновлений интерфейса из фоновых потоков.
        self.ui_queue: "queue.Queue" = queue.Queue()

        self.connected = False
        self._device_name = None
        self._device_address = None

        # IGate instance + state
        # Russian: экземпляр IGate и его состояние.
        self._igate = None
        self._igate_running = False

        self._build_ui()
        self._wire_callbacks()
        self.root.after(100, self._poll_queue)

    # ------------------------------------------------------------ UI building
    # Russian: построение всех виджетов окна.
    # English: builds all window widgets.
    def _build_ui(self):
        pad = {"padx": 6, "pady": 4}

        # --- tabbed layout / вкладки
        self.nb = ttk.Notebook(self.root)
        self.nb.pack(fill="x", padx=8, pady=(6, 0))
        tab1 = ttk.Frame(self.nb)
        tab2 = ttk.Frame(self.nb)
        tab1.configure(height=320)
        tab2.configure(height=320)
        self.nb.add(tab1, text="TNC & TX")
        self.nb.add(tab2, text="Server & IGate")

        # ============ Tab 1: device + transmit ============
        # --- top: device selection / выбор устройства
        top = ttk.LabelFrame(tab1, text="Device (TD-H9 BLE radio)")
        top.pack(fill="x", padx=8, pady=6)

        row = ttk.Frame(top)
        row.pack(fill="x", **pad)

        self.btn_scan = ttk.Button(row, text="Scan", command=self._scan)
        self.btn_scan.pack(side="left")

        self.device_list = ttk.Combobox(row, width=52, state="readonly")
        self.device_list.pack(side="left", padx=6)

        self.btn_connect = ttk.Button(row, text="Connect", command=self._connect,
                                      state="disabled")
        self.btn_connect.pack(side="left", padx=6)

        self.btn_dev_mru = ttk.Button(row, text="History \u25be", command=self._show_dev_mru)
        self.btn_dev_mru.pack(side="left", padx=6)

        self.btn_disconnect = ttk.Button(row, text="Disconnect", command=self._disconnect,
                                         state="disabled")
        self.btn_disconnect.pack(side="left")

        self.status = ttk.Label(top, text="Not connected", foreground="gray")
        self.status.pack(fill="x", **pad)

        # --- TX section / блок передачи
        tx = ttk.LabelFrame(tab1, text="Transmit (APRS)")
        tx.pack(fill="x", padx=8, pady=6)

        trow = ttk.Frame(tx)
        trow.pack(fill="x", **pad)
        ttk.Label(trow, text="From (call-SSID):").pack(side="left")
        self.src_var = tk.StringVar(value="URCALL-7")
        ttk.Entry(trow, textvariable=self.src_var, width=14).pack(side="left", padx=4)
        ttk.Label(trow, text="To:").pack(side="left")
        self.dst_var = tk.StringVar(value="APZ001")
        ttk.Entry(trow, textvariable=self.dst_var, width=10).pack(side="left", padx=4)
        ttk.Label(trow, text="Comment:").pack(side="left")
        self.msg_var = tk.StringVar(value="Test from KISS BLE")
        ttk.Entry(trow, textvariable=self.msg_var, width=26).pack(side="left", padx=4)

        brow = ttk.Frame(tx)
        brow.pack(fill="x", **pad)
        self.btn_send = ttk.Button(brow, text="Send", command=self._send, state="disabled")
        self.btn_send.pack(side="left")
        self.btn_send_mru = ttk.Button(brow, text="History \u25be", command=self._show_sent_mru)
        self.btn_send_mru.pack(side="left", padx=6)
        ttk.Label(brow, text="(or paste a raw APRS text frame below)").pack(side="left", padx=6)

        ttk.Label(tx, text="Raw APRS frame (takes priority over the fields above):").pack(
            fill="x", padx=6)
        self.raw_frame_var = tk.StringVar()
        ttk.Entry(tx, textvariable=self.raw_frame_var).pack(fill="x", padx=6, pady=(0, 4))

        # ============ Tab 2: server + IGate ============
        # --- KISS TCP server / KISS-сервер
        server = ttk.LabelFrame(tab2, text="BLE KISS TNC over TCP/IP")
        server.pack(fill="x", padx=8, pady=6)

        srow = ttk.Frame(server)
        srow.pack(fill="x", **pad)

        ttk.Label(srow, text="Port:").pack(side="left")
        self.port_var = tk.StringVar(value="8023")
        ttk.Entry(srow, textvariable=self.port_var, width=8).pack(side="left", padx=4)

        ttk.Label(srow, text="Mode:").pack(side="left")
        self.mode_var = tk.StringVar(value="Binary KISS")
        self.mode_combo = ttk.Combobox(srow, textvariable=self.mode_var, width=16,
                                       state="readonly",
                                       values=["Binary KISS", "AGW (AGWPE)", "APRS-IS"])
        self.mode_combo.pack(side="left", padx=4)

        self.btn_server = ttk.Button(srow, text="Start server", command=self._toggle_server)
        self.btn_server.pack(side="left", padx=6)
        self.btn_preset = ttk.Button(srow, text="Presets \u25be", command=self._show_presets)
        self.btn_preset.pack(side="left", padx=6)
        self.server_state = ttk.Label(srow, text="Server stopped", foreground="gray")
        self.server_state.pack(side="left", padx=6)

        # client list display (Listbox) / список клиентов
        self.clients_frame = ttk.Frame(server)
        self.clients_frame.pack(fill="x", padx=6, pady=(0, 4))
        self.clients_scroll = ttk.Scrollbar(self.clients_frame, orient="vertical")
        self.clients_listbox = tk.Listbox(self.clients_frame, height=4,
                                          activestyle="none",
                                          yscrollcommand=self.clients_scroll.set)
        self.clients_scroll.config(command=self.clients_listbox.yview)
        self.clients_scroll.pack(side="right", fill="y")
        self.clients_listbox.pack(side="left", fill="x", expand=True)

        # --- IGate settings form / форма настроек IGate
        ig = ttk.LabelFrame(tab2, text="IGate (Radio <-> APRS-IS)")
        ig.pack(fill="x", padx=8, pady=6)

        self.igate_settings = load_settings()
        _c = self.igate_settings

        igrow1 = ttk.Frame(ig)
        igrow1.pack(fill="x", padx=6, pady=2)
        ttk.Label(igrow1, text="Client (APRSIS_CLIENT):").pack(side="left")
        self.ig_client_var = tk.StringVar(value=_c.get("aprsis_client", "NOCALL-10"))
        ttk.Entry(igrow1, textvariable=self.ig_client_var, width=12).pack(side="left", padx=4)
        ttk.Label(igrow1, text="Name (IGATE_NAME):").pack(side="left")
        self.ig_name_var = tk.StringVar(value=_c.get("igate_name", "NOCALL-1"))
        ttk.Entry(igrow1, textvariable=self.ig_name_var, width=12).pack(side="left", padx=4)
        ttk.Label(igrow1, text="Passcode:").pack(side="left")
        self.ig_pass_var = tk.StringVar(value=str(_c.get("passcode", 0)))
        ttk.Entry(igrow1, textvariable=self.ig_pass_var, width=8).pack(side="left", padx=4)

        igrow2 = ttk.Frame(ig)
        igrow2.pack(fill="x", padx=6, pady=2)
        ttk.Label(igrow2, text="Server:").pack(side="left")
        self.ig_server_var = tk.StringVar(value=_c.get("server", "rotate.aprs2.net"))
        ttk.Entry(igrow2, textvariable=self.ig_server_var, width=20).pack(side="left", padx=4)
        ttk.Label(igrow2, text="Port:").pack(side="left")
        self.ig_port_var = tk.StringVar(value=str(_c.get("port", 14580)))
        ttk.Entry(igrow2, textvariable=self.ig_port_var, width=6).pack(side="left", padx=4)
        ttk.Label(igrow2, text="Filter:").pack(side="left")
        default_name = (_c.get("igate_name", "NOCALL-1") or "NOCALL-1").upper()
        default_filter = f"d/{default_name.split('-', 1)[0]}*"
        self.ig_filter_var = tk.StringVar(value=_c.get("filter", default_filter).strip() or default_filter)
        ttk.Entry(igrow2, textvariable=self.ig_filter_var, width=26).pack(side="left", padx=4)

        igrow3 = ttk.Frame(ig)
        igrow3.pack(fill="x", padx=6, pady=2)
        self.ig_tcpip_var = tk.BooleanVar(value=bool(_c.get("check_tcpip", True)))
        ttk.Checkbutton(igrow3, text="Require TCPIP",
                        variable=self.ig_tcpip_var).pack(side="left", padx=6)
        self.ig_noqar_var = tk.BooleanVar(value=bool(_c.get("check_no_qar", True)))
        ttk.Checkbutton(igrow3, text="Reject qAR",
                        variable=self.ig_noqar_var).pack(side="left", padx=6)
        self.ig_noqao_var = tk.BooleanVar(value=bool(_c.get("check_no_qao", True)))
        ttk.Checkbutton(igrow3, text="Reject qAO",
                        variable=self.ig_noqao_var).pack(side="left", padx=6)
        self.btn_igate = ttk.Button(igrow3, text="Start", command=self._igate_toggle)
        self.btn_igate.pack(side="right", padx=2)
        self.ig_state = ttk.Label(ig, text="IGate stopped", foreground="gray")
        self.ig_state.pack(fill="x", padx=6, pady=(0, 4))

        # ============ Log window at the bottom / лог внизу ============
        # --- RX/TX log / окно приёма и передачи
        rx = ttk.LabelFrame(self.root, text="RX/TX Log")
        rx.pack(fill="both", expand=True, padx=8, pady=6)

        rx_head = ttk.Frame(rx)
        rx_head.pack(fill="x", padx=4, pady=(4, 0))
        # Russian: текст можно выделять и копировать (Ctrl+C).
        ttk.Label(rx_head, text="(text is selectable and copyable via Ctrl+C)").pack(side="left")
        ttk.Button(rx_head, text="Clear", command=self._clear_rx).pack(side="right")

        self.rx_log_frame = ttk.Frame(rx)
        self.rx_log_frame.pack(fill="both", expand=True, padx=4, pady=4)
        self.rx_scroll = ttk.Scrollbar(self.rx_log_frame, orient="vertical")
        self.rx_text = tk.Text(self.rx_log_frame, height=12, wrap="word",
                               yscrollcommand=self.rx_scroll.set)
        self.rx_scroll.config(command=self.rx_text.yview)
        self.rx_scroll.pack(side="right", fill="y")
        self.rx_text.pack(side="left", fill="both", expand=True)
        self.rx_text.configure(state="disabled")

        # Allow selection + copy (Ctrl+C / Ctrl+A / Ctrl+Shift+Insert) but block
        # typing and deletion on ordinary (non-copy) key presses.
        # Russian: разрешаем выделение и копирование, но блокируем ввод и удаление.
        def _block_non_copy(event):
            ctrl = (event.state & 0x0004) != 0  # Control modifier pressed
            if ctrl and event.keysym.lower() in ("c", "a", "insert"):
                return None
            return "break"

        for key in ("<Key>", "<BackSpace>", "<Delete>", "<Return>", "<Insert>"):
            self.rx_text.bind(key, _block_non_copy)

    # ------------------------------------------- wire BLE callbacks / колбэки
    def _wire_callbacks(self):
        self.ble.on_scan_result = self._on_scan_done
        self.ble.on_connected = self._on_connected
        self.ble.on_disconnected = self._on_disconnected
        self.ble.on_connect_error = self._on_ble_error
        self.ble.on_rx = self._on_ble_rx
        self.ble.on_services = self._on_services

    # ---------------------------------------------------------- UI queue pump
    # Russian: периодически выполняет отложенные обновления интерфейса.
    # English: periodically executes deferred UI updates posted from threads.
    def _poll_queue(self):
        try:
            while True:
                fn = self.ui_queue.get_nowait()
                fn()
        except queue.Empty:
            pass
        self.root.after(100, self._poll_queue)

    # Russian: обновляет список клиентов сервера (по событию подкл/откл).
    # English: refreshes the server client list (on connect/disconnect event).
    def _on_clients_changed(self):
        # Called from a server thread on connect/disconnect; schedule the
        # UI refresh on the main thread.
        # Russian: фоновый поток сервера -> обновляем UI в главном потоке.
        try:
            self._bus(self._refresh_clients)
        except Exception:
            pass

    def _refresh_clients(self):
        entries = []
        servers = [("kiss", self.server), ("agw", self.agw_server), ("aprs", self.aprsis_server)]
        for proto, srv in servers:
            try:
                for cl in srv.client_list():
                    callsign = cl.get("callsign", "") or ""
                    addr = cl.get("addr", "?")
                    port = cl.get("port", 0)
                    mode = "/tx" if cl.get("can_tx", True) else "/rx"
                    # If the callsign is unknown, omit it entirely (no '?@').
                    # Russian: если позывной неизвестен, не выводим '?@'.
                    if callsign:
                        entries.append(f"{proto}://{callsign}@{addr}:{port}{mode}")
                    else:
                        entries.append(f"{proto}://{addr}:{port}{mode}")
            except Exception:
                pass
        # rebuild the listbox contents
        self.clients_listbox.delete(0, tk.END)
        for e in entries:
            self.clients_listbox.insert(tk.END, e)

    def _bus(self, fn, *args):
        """Post fn(*args) for execution on the UI thread."""
        # Russian: постить задачу в UI-поток.
        def wrap():
            fn(*args)
        self.ui_queue.put(wrap)

    # ------------------------------------------------------------ log helpers
    # Russian: вспомогательные функции окна приёма.
    # English: receive-window helper methods.
    MAX_LOG_LINES = 2000  # keep at most this many lines in the window

    def _log_rx(self, text: str):
        """Append a line with a timestamp; prune old lines to MAX_LOG_LINES.

        Russian:  Добавляет строку с временной меткой и обрезает старые
                  строки до MAX_LOG_LINES.
        English:  Appends a timestamped line and prunes to MAX_LOG_LINES.
        """
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        line = f"[{ts}] {text}"
        self.rx_text.configure(state="normal")
        self.rx_text.insert(tk.END, line + "\n")
        # Trim the oldest lines so the window does not grow unbounded.
        # Russian: обрезаем старые строки, чтобы окно не разрасталось бесконечно.
        while int(self.rx_text.index("end-1c").split(".")[0]) > self.MAX_LOG_LINES:
            self.rx_text.delete("1.0", "2.0")
        self.rx_text.see(tk.END)
        self.rx_text.configure(state="disabled")

    def _clear_rx(self):
        self.rx_text.configure(state="normal")
        self.rx_text.delete("1.0", tk.END)
        self.rx_text.configure(state="disabled")

    def _agw_debug_frame(self, kind, cfrom, cto, pid, data):
        """Debug hook: show raw inbound AGW frames in the RX log.

        Russian:  Отладка AGW — показывает сырые кадры клиента в окне лога.
        English:  Debug dump of every inbound AGW frame.
        """
        summary = f"kind='{kind}' from='{cfrom}' to='{cto}' pid=0x{pid or 0:02X} len={len(data)} hex={data.hex()}"
        self._bus(self._log_rx, f"[AGW in] {summary}")

    def _log_server_tx(self, data: bytes):
        # data depends on the active mode:
        #  - KISS binary: raw KISS frame (0xC0 ... ) -> show parsed APRS text.
        #  - AGW: full AGW frame (36-byte header + monitored data) -> show text.
        if getattr(self, "_server_kind", None) == "agw" and len(data) > 36:
            # AGW monitored-unproto payload:
            #   " 1:Fm SRC To DST Via DIGIS <UI ... >[time]\r<info>\r\0"
            body = bytes(data[36:])
            sep = body.find(b"\r")
            if sep != -1:
                preamble = body[:sep].decode("utf-8", errors="replace")
                info = body[sep + 1:].decode("utf-8", errors="replace")
                txt = (preamble + "  " + info).strip()
            else:
                txt = to_aprs_text(body) or f"</hex: {body.hex()}>"
        else:
            if data[:1] == b"\xc0":  # KISS-wrapped
                # strip trailing/leading FEND for display
                body = data.strip(b"\xc0")
                txt = to_aprs_text(body) or f"</hex: {data.hex()}>"
            else:
                txt = data.decode("utf-8", errors="replace").strip() or "</empty>"
        self._bus(self._log_rx, f"[TCP -> client] {txt}")

    # --------------------------------------------------------------- scanning
    # Russian: сканирование BLE-устройств.
    def _scan(self):
        self.btn_scan.configure(state="disabled")
        self.status.configure(text="Scanning...", foreground="orange")
        threading.Thread(target=self.ble.scan, daemon=True).start()

    def _on_scan_done(self, devices):
        def upd():
            self.btn_scan.configure(state="normal")
            if not devices:
                self.status.configure(text="No devices found", foreground="red")
                return
            self._devices = devices
            labels = [d.label for d in devices]
            self.device_list["values"] = labels
            self.device_list.current(0)
            self.btn_connect.configure(state="normal")
            self.status.configure(
                text=f"Devices found: {len(devices)}", foreground="green")
        self._bus(upd)

    def _get_selected_device(self):
        """Return the currently selected device or None."""
        # Russian: возвращает выбранное устройство.
        idx = self.device_list.current()
        if idx < 0 or not hasattr(self, "_devices") or idx >= len(self._devices):
            return None
        return self._devices[idx]

    # -------------------------------------------------------------- connecting
    # Russian: подключение/отключение от BLE-устройства.
    def _connect(self):
        dev = self._get_selected_device()
        if dev is None:
            messagebox.showwarning("Attention", "Scan first and select a device.")
            return
        self.btn_connect.configure(state="disabled")
        self.status.configure(text=f"Connecting to {dev.label}...", foreground="orange")
        threading.Thread(target=self.ble.connect, args=(dev.address,), daemon=True).start()

    def _on_connected(self, address, name):
        def upd():
            self.connected = True
            self._device_address = address
            self._device_name = name
            self.btn_disconnect.configure(state="normal")
            self.btn_connect.configure(state="disabled")
            self.btn_send.configure(state="normal")
            self.status.configure(text=f"Connected: {name} ({address})", foreground="green")
            self._log_rx(f"[BLE] Connected to {name} ({address})")
            mru_store.record_connected_device(name, address)
        self._bus(upd)

    def _disconnect(self):
        self.connected = False
        self._device_address = None
        self._device_name = None
        self.btn_send.configure(state="disabled")
        self.btn_disconnect.configure(state="disabled")
        self.btn_connect.configure(state="normal")
        self.status.configure(text="Disconnected", foreground="gray")
        threading.Thread(target=self.ble.disconnect, daemon=True).start()

    def _on_disconnected(self):
        def upd():
            self.connected = False
            self._device_address = None
            self._device_name = None
            self.btn_send.configure(state="disabled")
            self.btn_disconnect.configure(state="disabled")
            self.btn_connect.configure(state="normal")
            self.status.configure(text="Disconnected", foreground="gray")
            self._log_rx("[BLE] Connection lost")
        self._bus(upd)

    def _on_ble_error(self, msg):
        def upd():
            self.btn_scan.configure(state="normal")
            self.btn_connect.configure(state="normal")
            self.status.configure(text=f"Error: {msg}", foreground="red")
            self._log_rx(f"[BLE!] {msg}")
        self._bus(upd)

    # Russian: сохранение характеристик устройства в devcfg_<addr>.json.
    def _on_services(self, summary, write_uuid, write_handle, notify_uuid,
                     notify_handle, char_records):
        def upd():
            if self.ble.current_address:
                mru_store.save_device_config(self.ble.current_address, char_records)
            self._log_rx("[BLE] Discovered characteristics (service -> char -> props):")
            for s in summary:
                self._log_rx(f"      {s}")
            self._log_rx(f"[BLE] Write: {write_uuid}  (handle {write_handle})")
            self._log_rx(f"[BLE] Notify: {notify_uuid}  (handle {notify_handle})")
        self._bus(upd)

    # -------------------------------------------------------- incoming KISS data
    # Russian: приём KISS-фреймов по BLE и их отображение.
    def _on_ble_rx(self, data: bytes):
        # feed the KISS parser -> on _on_kiss_frame
        self.parser.feed(bytes(data))

    def _on_kiss_frame(self, port, command, payload):
        # payload = binary AX.25 frame (or plain APRS text)
        try:
            txt = to_aprs_text(payload)
        except Exception:
            txt = None
        if not txt or not txt.strip():
            return
        txt = txt.strip()
        # log received packet (rx_<addr>_<date>.json)
        if self.ble.current_address:
            try:
                packet_log.log_rx(self.ble.current_address, txt, self._device_name or "")
            except Exception:
                pass
        try:
            aprs = parse_aprs(txt)
            display = aprs.to_multiline()
        except Exception:
            display = f"Raw: {txt} (cmd={command})"
        self._bus(self._log_rx, f"[RX] {display}")

        # forward the raw AX.25/APRS payload to connected TCP servers
        # (KISS binary, AGW or APRS-IS each frame it appropriately)
        raw = bytes(payload)
        try:
            self.server.broadcast(raw)
        except Exception:
            pass
        try:
            self.agw_server.broadcast(raw)
        except Exception:
            pass
        try:
            self.aprsis_server.broadcast(raw)
        except Exception:
            pass
        # feed the decoded frame to the IGate (radio -> network, rule b)
        # Russian: передаём принятый кадр в IGate (радио -> сеть, правило b).
        try:
            self._igate_radio_rx(txt.encode("utf-8"))
        except Exception:
            pass

    # ------------------------------------------------------------------ sending
    # Russian: отправка APRS-фрейма через BLE.
    def _send(self):
        if not self.connected:
            messagebox.showwarning("Attention", "Connect to a BLE device first.")
            return
        frame = self._build_frame()
        if not frame:
            return
        # record the human-readable frame for the MRU history and TX log
        raw_graphic = self._current_send_text()
        if raw_graphic:
            mru_store.record_sent_message(
                raw_graphic, self.ble.current_address or "", self._device_name or "")
            if self.ble.current_address:
                try:
                    packet_log.log_tx(self.ble.current_address, raw_graphic,
                                      self._device_name or "")
                except Exception:
                    pass
        kiss_frame = frame_kiss(frame)
        threading.Thread(target=self.ble.send_raw, args=(kiss_frame,), daemon=True).start()

    def _current_send_text(self) -> str:
        """Return the frame text as shown in the TX fields (for history/logs)."""
        raw = self.raw_frame_var.get().strip()
        if raw:
            return raw
        src = self.src_var.get().strip()
        dst = self.dst_var.get().strip()
        msg = self.msg_var.get().strip()
        body = f"{src}>{dst}"
        body += ":" + msg if msg else ":"
        return body

    # Russian: сборка бинарного AX.25-фрейма из полей ввода.
    # English: builds a binary AX.25 frame from the input fields.
    def _build_frame(self) -> bytes:
        src = self.src_var.get().strip()
        dst = self.dst_var.get().strip()
        msg = self.msg_var.get().strip()
        raw = self.raw_frame_var.get().strip()

        # Priority: a filled raw frame is sent as-is.
        # Russian: приоритет — если заполнен сырой APRS-фрейм, отправляем его.
        if raw:
            if ">" not in raw:
                messagebox.showwarning("Attention", "Raw frame must contain 'CALL>DST:...'")
                return b""
            return encode_ax25_text(raw)

        # Otherwise assemble the frame from From/To/Comment.
        # Russian: иначе собираем фрейм из полей «От кого / Кому / Комментарий».
        if not src or not dst:
            messagebox.showwarning("Attention", "Enter 'From' and 'To' (or a raw frame).")
            return b""
        body = f"{src}>{dst}"
        body += ":" + msg if msg else ":"
        return encode_ax25_text(body)

    # Russian: передача данных от TCP-клиента в радио по BLE.
    def _client_tx(self, data: bytes):
        """Data received from a TCP client (KISS binary or AGW) became a raw
        AX.25 payload; transmit it to the radio over BLE.

        Russian:  Данные от TCP-клиента (KISS/AGW) — уже бинарный AX.25-кадр,
                  отправляем его в радио по BLE.
        """
        if not self.connected or not data:
            return
        ax25 = bytes(data)
        show = to_aprs_text(ax25) or f"</hex: {ax25.hex()}>"
        self._bus(self._log_rx, f"[TCP <- client] {show}")
        if self.ble.current_address:
            try:
                packet_log.log_tx(self.ble.current_address, show, self._device_name or "")
            except Exception:
                pass
        kiss_frame = frame_kiss(ax25)
        threading.Thread(target=self.ble.send_raw, args=(kiss_frame,), daemon=True).start()

    # Russian: передача данных от APRS-IS клиента в радио по BLE.
    def _client_tx_aprs(self, data: bytes):
        """Data received from an APRS-IS client -> transmit to radio over BLE.

        APRS-IS clients send text frames 'CALL>DST:info'. Comments ('#'-lines)
        are already filtered by the server and never reach here. The text is
        encoded into a binary AX.25 frame and written to the radio.

        Russian:  Данные от APRS-IS клиента (текст) кодируются в бинарный
                  AX.25-кадр и отправляются в радио по BLE. Комментарии '#'
                  отфильтрованы сервером и сюда не доходят.
        """
        if not self.connected or not data:
            return
        txt = data.decode("utf-8", errors="replace").strip()
        if not txt or txt.startswith("#"):
            return
        self._bus(self._log_rx, f"[APRS-IS <- client] {txt}")
        if self.ble.current_address:
            try:
                packet_log.log_tx(self.ble.current_address, txt, self._device_name or "")
            except Exception:
                pass
        try:
            ax25 = encode_ax25_text(txt)
        except Exception as e:
            self._bus(self._log_rx, f"[APRS-IS!] Failed to build frame: {e}")
            return
        kiss_frame = frame_kiss(ax25)
        threading.Thread(target=self.ble.send_raw, args=(kiss_frame,), daemon=True).start()

    # ----------------------------------------------------------- MRU histories
    # Russian: история подключённых устройств (MRU).
    def _show_dev_mru(self):
        devs = mru_store.load_connected_devices()
        if not devs:
            messagebox.showinfo("Device history", "Connection history is empty.")
            return
        self._show_menu_menu(self.btn_dev_mru, [
            (f"{d.get('name') or '<no name>'} ({d.get('address')})",
             f"{d.get('last_seen', '')}",
             lambda a=d.get('address'): self._connect_by_address(a))
            for d in devs
        ])

    # Russian: подключение к устройству из истории с загрузкой сохранённого конфига.
    def _connect_by_address(self, address):
        preset = mru_store.load_device_config(address)
        if preset:
            self.ble.apply_preset(preset)
            self._log_rx(f"[BLE] Loaded saved config for {address}: {len(preset)} characteristics")
        self.ble.connect(address)
        self.btn_connect.configure(state="disabled")
        self.status.configure(text=f"Connecting to {address} (from history)...",
                              foreground="orange")

    # Russian: история отправленных сообщений (MRU).
    def _show_sent_mru(self):
        msgs = mru_store.load_sent_messages()
        if not msgs:
            messagebox.showinfo("Message history", "Sent-message history is empty.")
            return
        self._show_menu_menu(self.btn_send_mru, [
            (m.get('frame', '')[:44],
             f"{m.get('name') or m.get('address') or '?'} {m.get('dt', '')}",
             lambda fr=m.get('frame'): self._fill_send_from_history(fr))
            for m in msgs
        ])

    # Russian: подстановка сообщения из истории в поле «Сырой APRS-фрейм».
    def _fill_send_from_history(self, frame):
        self.raw_frame_var.set(frame)

    def _show_menu_menu(self, anchor, items):
        """Show a popup Menu anchored at the given widget.

        items: list of (label, sublabel, callback). label+': '+sublabel shown.
        Russian: всплывающее меню у заданного виджета.
        """
        menu = tk.Menu(self.root, tearoff=0)
        for label, sublabel, cb in items:
            text = f"{label}" + (f"  [{sublabel}]" if sublabel else "")
            menu.add_command(label=text, command=cb)
        try:
            menu.tk_popup(anchor.winfo_rootx(),
                          anchor.winfo_rooty() + anchor.winfo_height())
        finally:
            menu.grab_release()

    # ---------------------------------------------------------------- server control
    # Russian: управление KISS/AGW сервером.
    @property
    def server_running(self):
        return getattr(self, "_server_on", False)

    def _active_mode(self):
        """Return the currently selected server mode ('kiss','agw' or 'aprs')."""
        val = self.mode_var.get().lower()
        if val.startswith("agw"):
            return "agw"
        if val.startswith("aprs"):
            return "aprs"
        return "kiss"

    # Russian: пресеты сервера — применяют готовый порт и режим.
    # English: server presets - apply a ready port + mode combo.
    def _show_presets(self):
        presets = [
            ("KISS Binary (8023)", "Binary KISS", "8023"),
            ("AGW (AGWPE) (8000)", "AGW (AGWPE)", "8000"),
            ("APRS-IS (14580)", "APRS-IS", "14580"),
        ]
        self._show_menu_menu(self.btn_preset, [
            (label, "",
             lambda m=mode, p=port: self._apply_preset(m, p))
            for label, mode, port in presets
        ])

    def _apply_preset(self, mode: str, port: str):
        """Set the mode+port fields from a preset and (re)start the server."""
        self.port_var.set(port)
        self.mode_var.set(mode)
        # if the server is running, restart it with the new settings
        if self.server_running:
            self._toggle_server()  # stop
            self._toggle_server()  # start with new mode/port

    def _toggle_server(self):
        if self.server_running:
            self.server.stop()
            kind = getattr(self, "_server_kind", None)
            if kind == "agw":
                self.agw_server.stop()
            elif kind == "aprs":
                self.aprsis_server.stop()
            self._server_on = False
            self._server_kind = None
            self.btn_server.configure(text="Start server")
            self.server_state.configure(text="Server stopped", foreground="gray")
        else:
            mode = self._active_mode()
            try:
                port = int(self.port_var.get())
                if mode == "agw":
                    self.agw_server.port = port
                    self.agw_server.start()
                elif mode == "aprs":
                    self.aprsis_server.port = port
                    self.aprsis_server.start()
                else:
                    self.server.port = port
                    self.server.start()
            except Exception as e:
                messagebox.showerror("Error", f"Failed to start server: {e}")
                return
            self._server_on = True
            self._server_kind = mode
            self.btn_server.configure(text="Stop server")
            if mode == "agw":
                srv = self.agw_server
            elif mode == "aprs":
                srv = self.aprsis_server
            else:
                srv = self.server
            self.server_state.configure(
                text=f"Listening on {srv.address} [{mode}]", foreground="green")

    # ---------------------------------------------------------------- IGate
    # Russian: сохранение настроек IGate в settings.json и управление IGate.
    # English: save IGate settings to settings.json and manage the IGate.
    def _igate_live_settings(self) -> dict:
        """Return current IGate settings straight from the GUI widgets.

        Used as settings_getter so toggling the flags/settings applies
        immediately without restarting the IGate.

        Russian:  Возвращает актуальные настройки IGate прямо из виджетов,
                  чтобы переключение применялось без перезапуска.
        """
        try:
            pc = int(self.ig_pass_var.get() or 0)
        except ValueError:
            pc = 0
        try:
            port = int(self.ig_port_var.get() or 14580)
        except ValueError:
            port = 14580
        return {
            "aprsis_client": self.ig_client_var.get().strip(),
            "igate_name": self.ig_name_var.get().strip(),
            "passcode": pc,
            "server": self.ig_server_var.get().strip(),
            "port": port,
            "filter": self.ig_filter_var.get().strip(),
            "enabled": True,
            "check_tcpip": bool(self.ig_tcpip_var.get()),
            "check_no_qar": bool(self.ig_noqar_var.get()),
            "check_no_qao": bool(self.ig_noqao_var.get()),
        }

    def _igate_live_settings(self) -> dict:
        """Build the IGate config straight from the GUI widgets.

        Russian:  Собирает конфиг IGate прямо из виджетов формы.
        """
        try:
            pc = int(self.ig_pass_var.get() or 0)
        except ValueError:
            pc = 0
        try:
            port = int(self.ig_port_var.get() or 14580)
        except ValueError:
            port = 14580
        cfg = {
            "aprsis_client": self.ig_client_var.get().strip(),
            "igate_name": self.ig_name_var.get().strip(),
            "passcode": pc,
            "server": self.ig_server_var.get().strip(),
            "port": port,
            "filter": self.ig_filter_var.get().strip(),
            "enabled": True,
            "check_tcpip": bool(self.ig_tcpip_var.get()),
            "check_no_qar": bool(self.ig_noqar_var.get()),
            "check_no_qao": bool(self.ig_noqao_var.get()),
        }
        return cfg

    def _collect_igate_cfg(self) -> dict:
        """Return the full IGate settings dict for starting/saving.

        Russian:  Возвращает полный набор настроек IGate для старта/сохранения.
        """
        return dict(self._igate_live_settings())

    def _persist_igate_settings(self, cfg: dict = None):
        """Save IGate settings to settings.json and update live IGate cfg.

        Russian:  Сохраняет настройки IGate в settings.json.
        """
        if cfg is None:
            cfg = self._collect_igate_cfg()
        self.igate_settings = dict(cfg)
        save_settings(cfg)
        if self._igate is not None:
            self._igate.cfg.update(cfg)

    def _igate_toggle(self):
        """Start or stop the IGate depending on current state.

        Starting applies the current GUI values and saves them; stopping
        just tears the connection down. All settings are persisted on start.

        Russian:  Запускает или останавливает IGate. При старте применяются
                  и сохраняются текущие значения формы.
        """
        if self._igate_running:
            self._igate_stop()
        else:
            self._igate_start()

    def _igate_start(self):
        cfg = self._collect_igate_cfg()
        cfg.update({"enabled": True})
        self.igate_settings = dict(cfg)
        save_settings(cfg)
        self._igate = IGate(
            settings=cfg,
            on_rx_to_radio=self._igate_to_radio,
            on_log=lambda m: self._bus(self._log_rx, f"[IGate] {m}"),
            settings_getter=self._igate_live_settings,
        )
        self._igate_running = True
        self._igate.start()
        self._log_rx("[IGate] started")
        self._update_igate_state()

    def _igate_stop(self):
        if self._igate is not None:
            self._igate.stop()
            self._igate = None
        self._igate_running = False
        self._log_rx("[IGate] stopped")
        self._update_igate_state()

    def _igate_to_radio(self, frame: bytes):
        """A network frame was gated to the radio -> transmit it over BLE.

        Always logs the frame, even if no radio is connected yet, so the
        traffic is visible in the window.

        Russian:  Сетевой кадр, допущенный к радио, уходит в BLE. Логируем
                  его всегда, даже если радио пока не подключено.
        """
        txt = frame.decode("utf-8", errors="replace").strip()
        self._bus(self._log_rx, f"[IGate -> radio] {txt}")
        if not self.connected:
            self._bus(self._log_rx, "[IGate!] radio not connected, frame not transmitted")
            return
        try:
            ax25 = encode_ax25_text(txt)
        except Exception as e:
            self._bus(self._log_rx, f"[IGate!] {e}")
            return
        if self.ble.current_address:
            try:
                packet_log.log_tx(self.ble.current_address, txt, self._device_name or "")
            except Exception:
                pass
        kiss_frame = frame_kiss(ax25)
        threading.Thread(target=self.ble.send_raw, args=(kiss_frame,), daemon=True).start()

    def _igate_radio_rx(self, frame: bytes):
        """A frame received from the radio -> feed it to the IGate (if enabled)."""
        # Russian: кадр из эфира передаётся в IGate (если включён).
        if self._igate_running and self._igate is not None:
            try:
                self._igate.radio_rx(frame)
            except Exception:
                pass

    def _update_igate_state(self):
        state = "IGate running" if self._igate_running else "IGate stopped"
        col = "#2e7d32" if self._igate_running else "gray"
        if hasattr(self, "ig_state"):
            self.ig_state.configure(text=state, foreground=col)
        if hasattr(self, "btn_igate"):
            self.btn_igate.configure(text="Stop" if self._igate_running else "Start")

    # ------------------------------------------------------------------ shutdown
    # Russian: корректное завершение работы приложения.
    def _close(self):
        # persist current IGate settings on close / сохраняем настройки IGate
        try:
            self._persist_igate_settings(self._collect_igate_cfg())
        except Exception:
            pass
        try:
            self.server.stop()
        except Exception:
            pass
        try:
            self.agw_server.stop()
        except Exception:
            pass
        try:
            self.aprsis_server.stop()
        except Exception:
            pass
        try:
            self._igate_stop()
        except Exception:
            pass
        try:
            self.ble.close()
        except Exception:
            pass
        self.root.destroy()


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()