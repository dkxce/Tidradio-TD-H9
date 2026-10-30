<!-- markdown-translator:af3f80970e968b54a6453e1e90a3bff2035c190fb9d45a40a62262ce187c14fc -->
# TIDRadio TD-H9 · APRS KISS TNC BLE

[RU](README.md)|[IN](README.en.md)|[RELEASES](https://github.com/dkxce/Tidradio-TD-H9/releases)

The program turns the walkie-talkie**TIDRadio TD-H9**(and compatible firmware with BLE service
Odmaster) in**KISS-TNC-modem over Bluetooth Low Energy**. The walkie-talkie acts as
hardware TNC: it itself modulates/demodulates the 1200 baud AFSK signal, and the program
exchanges ready-made KISS/AX.25 frames with it via BLE. On top of this program
brings up TCP servers for external APRS applications and built-in IGate.

***

## 1. What is it and why

TIDRadio TD-H9 series radios do not transmit sound (AFSK) outward like regular TNC radios.
Instead, there is a built-in running inside**TNC**, which communicates with the outside
device via Bluetooth. This allows the PC to access APRS air without
audio cables and a separate TNC device.

The task of the program is to turn such a radio into a full-fledged TNC modem, with which
can work**any**APRS applications (maps, UI clients, digital feeders/igate).

```
текстовый APRS-кадр (SRC>DST,PATH:info)
      │  encode_ax25
      ▼
бинарный AX.25-кадр (адреса по 7 байт, control, PID, info)
      │  kiss_escape + FEND
      ▼
KISS-фрейм: [0xC0][port:cmd][escape(AX.25)][0xC0]
      │  BLE GATT write / notify
      ▼
рация TIDRadio (AFSK 1200 бод в эфир и обратно)
```

***

## 2. Opportunities

* **BLE connection to walkie-talkie**how to KISS-TNC (scanning, device history,
  auto-connection via MAC from memory).
* Exchange by**KISS protocol**(borders`0xC0`, escape`0xDB`/`0xDC`/`0xDD`).
* **Binary AX.25**⇄ text APRS: reception and transmission, accurate parsing without
  "krakozyabr"
* **Three TCP servers**simultaneously, selected by mode:
  * **Binary KISS**(port 8023) - raw KISS stream for TNC clients;
  * **AGWPE**(port 8000) - 36-byte headers, Dire Wolf format;
  * **APRS-IS**(port 14580) - text protocol with passcode checking.
* **Built-in IGate**— radio ⇄ APRS-IS (incoming and outgoing gating,
  filtering rules, autosaving settings).
* **Sending APRS**from GUI: From/To/Comment fields or raw frame, history (MRU).
* **Log RX/TX**with selection and copying, vertical scrolling.
* **List of connected clients**TCP servers with scrolling.
* **Logs of received/sent packets**в JSON (`packet_log`), device history
  and messages (`mru_store`).

***

## 3. Requirements

* Python**3.10+**(GUI on tkinter) or 3.11+.
* Library**bleak**for BLE (`pip install bleak`).
* Radio TIDRadio TD-H9 (or firmware with APRS service**0000af00**).
* Windows / macOS / Linux (tested on Windows).

***

## 4. Quick start

```bash
pip install bleak
cd tidradio_kiss
python main.py
```

1. Run`python main.py`.
2. In the ta&#x62;**«TNC & TX»**&#x63;lick**Scan**— select a radio from the list,
   click**Connect**.
3. Connect and make sure that services appear in the log (Write/Notify).
4. In the ta&#x62;**«Server & IGate»**&#x73;elect server mode and port, click**Start server**.
5. Connect an external APRS application (see the Compatibility section).
6. To transmit a package, fill in the Transmit fields and click**Send**, or
   transfer via a connected application.

***

## 5. Structure of the project

| File | Role |
|---|---|
|`main.py`| GUI (Tk), orchestration, two tabs, RX/TX log |
|`ble_radio.py`| BLE transport (bleak, asyncio in stream), performance resolution |
|`gatt_info.py`| description of services/characteristics of BLE GATT |
|`kiss.py`| KISS protocol (packing/unpacking frames) |
|`ax25.py`| binary AX.25 ⇄ readable APRS text |
|`aprs_parser.py`| parsing the contents of an APRS packet (position, message, etc.) |
|`kiss_tcp_server.py`| TCP-Server Binary KISS (8023) |
|`agw_server.py`| TCP server AGWPE / Dire Wolf (8000) |
|`aprsis_server.py`| TCP server APRS-IS (14580) |
|`igate.py`| built-in IGate (radio ⇄ APRS-IS), settings |
|`mru_store.py`| device and message history |
|`packet_log.py`| logs of received/sent packets |
|`aprsis_test.py`,`igate_test.py`| test clients (listener / IGate sender) |
|`settings.json`| IGate settings (in the module folder) |

***

## 6. BLE (services and characteristics)

The program uses the APRS service from the Odmaster application:

| Destination | UUID |
|---|---|
| APRS service |`0000af00-0000-1000-8000-00805f9b34fb`|
| TX (write) |`0000af01-0000-1000-8000-00805f9b34fb`(write-without-response) |
| RX (notify) |`0000af02-0000-1000-8000-00805f9b34fb`|

There are backup candidates for other firmware (`ff02`/`ffe2`for recording,`ff01`/`ffe1`for notify). Characteristic resolution occurs automatically when
connection; the found set is saved in`devcfg_<address>.json`for speed
reconnection.

***

## 7. TCP servers

You can run**one**server at the same time. The mode is selected in the GUI and through
presets:

| Mode | Default Port | Protocol | What is useful |
|---|---|---|---|
|`Binary KISS`| 8023 | raw KISS frames | hardware/software TNC clients |
|`AGW (AGWPE)`| 8000 | 36-byte AGW headers, Dire Wolf format | UISS, UI-View32, AGW clients |
|`APRS-IS`| 14580 | text APRS + login/passcode | network APRS clients and tests |

Incoming packets from the radio are sent to all connected clients in their
format (KISS bytes / AGW monitor / APRS-IS strings). Frames originating from the client
are encoded in AX.25 and sent to the radio via BLE.

### Binary KISS (kiss\_tcp\_server.py)

The client sends and receives raw KISS frames exactly like a serial TNC over the network.
No login. All clients can transfer.

### AGWPE (agw\_server.py)

Compatible with AGWPE TCP/IP protocol and format**Dire Wolf**(36 byte
title). Supports typical AGW queries:

* `R`— version (AGWPE 2005/127);
* `G`/`g`— information about the port and its capabilities;
* `X`— call sign registration;
* `m`/`k`— enable monitoring / raw frames;
* `V`/`M`— UI frame transmission (with / without digi);`K`— raw AX.25.

Receive: sends out monitor frames`U`in Dire Wolf format
(`" 1:Fm SRC To DST Via ... <UI pid=.. Len=.. >[HH:MM:SS]"`). This has been verified with
UISS clients and AGW clients.

### APRS-IS (aprsis\_server.py)

APRS-IS text protocol. The client logs in with the line`user CALLSIGN pass PASSCODE vers ... filter ...`.**Passcode required**and
checked using the standard APRS-IS algorithm; incorrect passcode gives only
broadcast reading (unverified). Comments`#`are not broadcast on the radio.

***

## 8. Built-in IGate

`igate.py`— an independent bridge between the APRS radio broadcast and the APRS-IS network:

* **Network → radio:**&#x61; packet is gated onto the air only if there is a`<IGATE_NAME>`and it passes the flags (Reject qAR/qAO, Require TCPIP).
* **Radio → network:**&#x69;s added to the path`,qAR,<IGATE_NAME>`and the package goes to
  APRS-IS.
* Client login:`user <APRSIS_CLIENT> pass <PASSCODE> vers TDH9KissIGate v1.0 filter <FILTER>`,
  default filter`d/<IGATE_NAME>*`(by addressee, without SSID).
* Flags are applied**on the fly**(without restart) thanks to live-getter.
* Settings are stored in`settings.json`next to the module and are saved when
  pressed**Start**and when closing the window.
* GUI has one button**Start/Stop**.

***

## 9. Compatible with APRS applications

The program transmits the radio via**three**interface, so it works with it
a wide range of desktop APRS applications.

### UISS

* Connects to the program as with**AGW-lift (AGWPE TCP/IP)**.
* In UISS select TNC/Communication:**AGW Packet Engine, TCP/IP**, specify the port**8000**(server in mode`AGW (AGWPE)`).
* UISS uses AGW version, port, and monitoring queries; transfer supported
  and receiving packages, positions and messages.

### UI-View32

* Connection via**AGWPE TCP/IP**(port 8000).
* In the UI-View32 settings, specify the interface**AGWPE**/**AGW TCP/IP**, host`127.0.0.1`(or where the program is running), port`8000`.
* Receive the entire broadcast via an AGW monitor and transmit via digital feeders.

### APRSIS32

* Connects via**TCP/IP**or how**AGW**(port 8000), or (in some
  assemblies) as KISS-TNC.
* Specify connection type**AGW**and server address; APRSIS32 will send AGW frames
  and accept monitoring.
* Can also work via**Binary KISS**(port 8023) as through regular TCP-TNC.

### KMZViewer (https://github.com/dkxce/KMZViewer)

* Application-viewer of maps/KMZ of the project author; receives APRS stream via
  interface that the program provides (KISS / AGW / APRS-IS).
* Configure the APRS source in KMZViewer to the local program server
  (eg APRS-IS`127.0.0.1:14580`or KISS).

### APRSWin (https://github.com/dkxce/APRSWin)

* Windows APRS client; connects to the program as to a TNC via**TCP**in mode**Binary KISS**(port 8023) or**AGW**(port 8000).
* Uses reading of the entire broadcast through the KISS/AGW monitor and transmission from the card.

### APRSAir (https://github.com/dkxce/APRSAIR)

* APRS client/program of the author; also works via local KISS/AGW/APRS-IS
  program interface.

> **Short:**&#x41;ll listed programs are connected externally via TCP.
> If they can**AGWPE**- use the mode`AGW (AGWPE)`(port 8000);
> if they are expecting**KISS-TNC по TCP**- mode`Binary KISS`(port 8023);
> and any APRS-IS-compatible mode`APRS-IS`(port 14580).

***

## 10. Data flow principle

```
        рация TIDRadio TD-H9 (TNC + AFSK 1200)
                    ▼  BLE GATT 0000af00 (write af01 / notify af02)
        ble_radio.py (bleak, asyncio)
                    ▼  KISS-фреймы
        kiss.py  ⇄  ax25.py  ⇄  aprs_parser.py
                    ▼
        main.py
     ┌──────────┼──────────┬──────────┐
 KISS(8023)  AGW(8000)  APRS-IS(14580)  IGate(радио APRS-IS)
     └──────────┼──────────┴──────────┘
        внешние APRS-клиенты / APRS-IS сеть
```

***

## 11. KISS and AX.25 format (quick reference)

* **KISS:** `FEND=0xC0`,`FESC=0xDB`,`TFEND=0xDC`,`TFESC=0xDD`; team
  bytes`0x01 TXDELAY`,`0x02 PERSIST`,`0x03 SLOTTIME`,`0x04 TXTAIL`,`0x05 FULLDUPLEX`,`0x06 SETHARDWARE`,`0xFF RETURN`.
* **AX.25 UI:**&#x63;ontrol`0x03`, PID`0xF0`; addresses - 7 bytes (6 characters
  shifted left + SSID/flag), call sign in upper/latin case.
* The program itself encodes text into binary AX.25 and vice versa, so clients
  APRS text frames are sufficient.

***

## 12. License and Attribution

Program -**author's project dkxce**(c) https://github.com/dkxce.\
Written for compatibility with TIDRadio TD-H9.
