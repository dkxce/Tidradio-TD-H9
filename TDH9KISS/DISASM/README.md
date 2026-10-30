# APRS через BLE: анализ приложения Odmaster и реализация TNC-модема на Python

**APK:** `Odmaster_2.6.4.apk`    
**Декомпиляция APK:** `Ajadx-gui`    
**Пакет APRS в APK:** `com.tid.aprs`    

В этом документе собрано полное описание того, как работает TNC-модем через
Bluetooth: сначала — как это сделано в стоковом приложении **Odmaster** (по
декомпилированному APK), затем — как это реализовано **программе на Python**. 
В конце — сравнение, схема потока данных и таблица ключевых констант.

---

## 0. Коротко: что такое «TNC-модем через BLE»

В рации **TIDRadio TD-H9** работает аппаратный **TNC** (Terminal Node Controller):
он сам модулирует/демодулирует AFSK-сигнал 1200 бод и обменивается с внешним
устройством (телефоном/ПК) **готовыми кадрами** по протоколу **KISS**.

Порядок данных всегда такой:

```
текстовый APRS-кадр (SRC>DST,PATH:info)
        │  encode_ax25
        ▼
бинарный AX.25-кадр (адреса выровнены по 7 байт, control, PID, info)
        │  kiss_escape + FEND
        ▼
KISS-фрейм:  [0xC0][port:cmd][escape(ax25)][0xC0]
        │  BLE GATT write / notify
        ▼
рация TIDRadio (AFSK в эфир и обратно)
```

BLE-обмен — это просто транспорт для KISS-фреймов: write-характеристика для
передачи в рацию (TX), notify-характеристика для приёма из рации (RX).

---

## 1. Как сделано в APK Odmaster

Odmaster использует модуль `com.tid.aprs`.      
Связь с рацией — по Bluetooth.     
Данные — KISS поверх AX.25.     
При необходимости IGate-ретрансляция по TCP.     

### 1.1 Два независимых Bluetooth-пути

| Путь | Механизм | Ключевые классы APK |
|---|---|---|
| 1. Классический Bluetooth | SPP RFCOMM, UUID `00001101-0000-1000-8000-00805F9B34FB` | `BluetoothTnc.java`, `AprsBlueActivity.java` |
| 2. BLE GATT | библиотека `cn.com.heaton.blelibrary`, сервис `0000af00-0000-1000-8000-00805f9b34fb` | `AprsSendMessageNetworkVM.java`, `AprsVM.java` |
| 3. Радио (AFSK) | звуковая AFSK-модуляция/демодуляция | `AprsAfskSendFragment.java`, `AprsAfskListFragment.java`, `afsk/*` |
| 4. Интернет (IGate) | TCP + EasySocket | `AprsNetworkTranFragment.java`, `MessageProtocol.java` |

### 1.2 Классический Bluetooth (SPP RFCOMM)

Фоновый поток `BtSocketThread` подключается по SPP:    

```java
private UUID SPP = UUID.fromString("00001101-0000-1000-8000-00805F9B34FB");
...
BluetoothSocket s = tnc.createRfcommSocketToServiceRecord(SPP);
s.connect();  // BluetoothTnc.java:133-135
```

Отправка пакета в рацию:    

```java
OutputStream out = socket.getOutputStream();
out.write(Kiss.FEND);          // 0xC0
out.write(Kiss.CMD_DATA);      // 0x00
out.write(aPRSPacket.toAX25Frame());  // бинарный AX.25
out.write(Kiss.FEND);          // 0xC0
out.flush();
```

Приём — разбор KISS-потока:     

`FEND=0xC0` граница, `FESC=0xDB` escape,    
`TFEND=0xDC`/`TFESC=0xDD`; на FEND вызываются `Parser.parseAX25(...)` и    
`Parser.parse(...)` (строки `BluetoothTnc.java:209-247`).

### 1.3 BLE GATT

Библиотека `cn.com.heaton.blelibrary`     
(классы `Ble`, `BleDevice`, `BleWriteCallback`, `BleNotifyCallback`), обёртка `BluUtils`.

**UUID для APRS (BLE GATT):**

| Назначение | UUID |
|---|---|
| Service APRS | `0000af00-0000-1000-8000-00805f9b34fb` |
| Characteristic TX (write) | `0000af01-0000-1000-8000-00805f9b34fb` |
| Characteristic RX (notify) | `0000af02-0000-1000-8000-00805f9b34fb` |

Отправка:     

```java
ByteArrayOutputStream baos = new ByteArrayOutputStream();
baos.write(BluetoothTnc.Kiss.FEND);
baos.write(BluetoothTnc.Kiss.CMD_DATA);
baos.write(bArr);                                  // AX.25-фрейм
baos.write(BluetoothTnc.Kiss.FEND);
BluUtils.getInstance().getmBle().writeByUuid(
    device, baos.toByteArray(),
    UUID.fromString("0000af00-0000-1000-8000-00805f9b34fb"),  // service
    UUID.fromString("0000af01-0000-1000-8000-00805f9b34fb"),  // write char
    callback);
```

Приём (notify):     

```java
BluUtils.getInstance().getmBle().enableNotifyByUuid(
    device, true,
    UUID.fromString("0000af00-0000-1000-8000-00805f9b34fb"),
    UUID.fromString("0000af02-0000-1000-8000-00805f9b34fb"),
    new BleNotifyCallback<BleDevice>() {
        void onChanged(BleDevice d, BluetoothGattCharacteristic c) {
            String s = AprsByteProcessor.getKissString(c.getValue()).trim();
            if (TextUtils.isEmpty(s) || !s.contains(">")) return;
            APRSPacket packet = Parser.parse(s);
            AprsStringUtil.addKiss(packet);     // список до 50 пакетов
            handler.sendMessage(...);          // обновление UI
        }
    });
```

### 1.4 Общие (не APRS) UUID рации `BluUtils.java`

| Назначение | UUID |
|---|---|
| Service рации | `0000ff00-0000-1000-8000-00805f9b34fb` |
| Write (команды) | `0000ff02-0000-1000-8000-00805f9b34fb` |
| Read | `0000ff01-0000-1000-8000-00805f9b34fb` |
| Notify (DX) | `0000ff21-0000-1000-8000-00805f9b34fb` |
| Write (DX) | `0000ff22-0000-1000-8000-00805f9b34fb` |

`BluUtils.init`:    

```java
Ble.options()
  .setUuidService ("0000ff00-...")
  .setUuidWriteCha("0000ff02-...")
  .setUuidReadCha ("0000ff01-...")
  .create(context, ...);
```

### 1.5 Интернет / IGate в APK

При `isRadioToNet() && isAutoConnect()` принятый пакет публикуется в RxBus
(`BluetoothTnc.java:35`, `AprsMainActivity.java:210-216`) и уходит в сеть через
TCP + EasySocket. В сети используется **текстовый** APRS (`AprsPacket.formatLogin`
+ позиция) по TCP с 1024-байтным протоколом чтения.

---

## 2. Как это реализовано на Python (TDH9KISS)

TDH9KISS повторяет BLE GATT-путь (сервис `af00`, write `af01`, notify
`af02`), но добавляет поверх мини-серверы (KISS/AGW/APRS-IS) и встроенный IGate,
чтобы с рацией могли работать внешние APRS-приложения и сеть.

### 2.1 Модули

| Модуль | Роль |
|---|---|
| `main.py` | GUI (Tk), оркестрация, две вкладки, лог RX/TX |
| `ble_radio.py` | BLE-транспорт: сканирование, подключение, чтение GATT-сервисов, отправка/приём кадров |
| `gatt_info.py` | человекочитаемые описания сервисов/характеристик GATT |
| `kiss.py` | KISS-протокол: escape/unescape, парсер фреймов |
| `ax25.py` | кодирование/декодирование бинарного AX.25 ⇄ текстового APRS |
| `aprs_parser.py` | разбор содержимого APRS-пакета (позиция, сообщение и т.д.) |
| `kiss_tcp_server.py` | KISS TNC над TCP (порт 8023) |
| `agw_server.py` | AGWPE-совместимый сервер (порт 8000, 36-байтные заголовки) |
| `aprsis_server.py` | APRS-IS-совместимый сервер (порт 14580), серверная проверка passcode |
| `igate.py` | IGate-клиент (радио ⇄ APRS-IS), правила гейтинга, settings.json |
| `mru_store.py`, `packet_log.py` | история устройств/сообщений и журналы приёма/передачи |
| `aprsis_test.py`, `igate_test.py` | тестовые скрипты (listener / IGate sender) |

### 2.2 BLE-транспорт (`ble_radio.py`)

Используется библиотека **bleak** (asyncio). Всё asyncio выполняется в отдельном
фоновом потоке (`ble-loop`), а результаты приходят в GUI через колбэки и очереди.

Ключевые UUID:

```python
SERVICE_APRS = "0000af00-0000-1000-8000-00805f9b34fb"  # Service APRS
CHAR_WRITE   = "0000af01-0000-1000-8000-00805f9b34fb"  # TX, write-without-response
CHAR_NOTIFY  = "0000af02-0000-1000-8000-00805f9b34fb"  # RX, notify
```

Есть резервные кандидаты на случай других прошивок TNC:

```python
FALLBACK_WRITE  = [af01, ff02, ffe2]
FALLBACK_NOTIFY = [af02, ff01, ffe1]
```

**Разрешение характеристик** (`_resolve_chars`):     

после подключения программа перечисляет все сервисы/характеристики устройства, ищет:     
- write-характеристику (`write` или `write-without-response`),     
- notify-характеристику (`notify`),     

с приоритетом знакомых UUID `af01`/`af02` в APRS-сервисе `af00`, иначе — первую
подходящую из других сервисов (для совместимости с прошивками TD-H9/SPP-вариантов).
Каждая найденная характеристика записывается в per-device конфиг    
`devcfg_<address>.json` (через `mru_store`) с человекочитаемым описанием из    
`gatt_info` (`used_in_app` отмечает используемые каналы).     

**Передача** (`_write_async`):     

выбирает режим ответа по свойствам характеристики:    

```python
if "write-without-response" in props and "write" not in props:
    use_response = False      # af01 — без ответа
else:
    use_response = "write" in props
```

пишет `bytearray(data)` (готовый KISS-фрейм).         

**Приём** (`start_notify` → `_on_notify`) отдаёт сырые байты в колбэк `on_rx`.

### 2.3 KISS-протокол (`kiss.py`)

Полностью соответствует спецификации и APK:

| Имя | Байт | Назначение |
|---|---|---|
| `FEND` | `0xC0` | граница кадра |
| `FESC` | `0xDB` | escape-префикс |
| `TFEND` | `0xDC` | экранированный FEND |
| `TFESC` | `0xDD` | экранированный FESC |

**Сборка кадра** `frame_kiss(ax25, port=0, cmd=CMD_DATA)`:

```python
cmd_byte = ((port & 0x0F) << 4) | (command & 0x0F)
body = bytes([cmd_byte]) + kiss_escape(ax25)
return bytes([FEND]) + body + bytes([FEND])
```

**Парсер** `KISSParser` — инкрементальный, обрабатывает байты по одному
(`feed`), корректно переживает разрыв escape-последовательности между TCP/BLE
порциями. На завершённом фрейме вызывает `on_frame(port, command, payload)`,
где `payload` — уже удалённые (de-escaped) bytes AX.25.

### 2.4 AX.25 APRS (`ax25.py`)

**AX.25-адрес** — 7 байт:

- `decode_ax25(data)` — разбор бинарного UI-фрейма.
- `encode_ax25_text(text)` — сборка бинарного UI-фрейма из текста.
- `to_aprs_text(data)` — если бинарный кадр — декодирует в `SRC>DST,..:info`;
  иначе возвращает сырые байты как ASCII (случай «рация уже отдала текст»).

Результат: любой принимаемый байтовый поток надёжно превращается в читаемый
APRS-текст без кракозябры (`\ufffd`).

### 2.5 Входящий поток (рация → ПК)

```
BLE notify (af02) → _on_ble_rx → KISSParser.feed
    → _on_kiss_frame(port, cmd, payload)
        → to_aprs_text(payload)  -> читаемый APRS-текст
        → parse_aprs → to_multiline() -> [RX] ... (лог)
        → broadcast(raw) на все TCP-серверы (KISS/AGW/APRS-IS)
        → _igate_radio_rx(text) — IGate, правило (b), радио → сеть
```

Каждый принятый пакет логируется в `rx_<addr>_<date>.json` и рассылается на все
подключённые клиенты TCP-серверов, каждый из которых упаковывает его по своему
протоколу (KISS-байты / AGW 36-байтный заголовок / text APRS).

### 2.6 Исходящий поток (ПК → рация)

Три источника, один путь в рацию по BLE:

| Источник | Обработка |
|---|---|
| Кнопка Send (поля From/To/Comment или Raw) | `_build_frame()` → `encode_ax25_text` → `frame_kiss` → `ble.send_raw` |
| KISS TCP-клиент | `_client_tx(ax25)` → `frame_kiss` → `ble.send_raw` |
| AGW TCP-клиент | `_client_tx(ax25)` (extract из 36-байтного заголовка) |
| APRS-IS клиент | `_client_tx_aprs(text)` → `encode_ax25_text` → `frame_kiss` → `ble.send_raw` |
| IGate (сеть → радио) | `_igate_to_radio(bytes)` → `frame_kiss` → `ble.send_raw` |

Все пути в итоге делают `frame_kiss(ax25) и `ble.send_raw(kiss_frame)`. Каждый
уходящий кадр пишется в `tx_...` журнал и в историю (MRU).

### 2.7 TCP-серверы (внешние APRS-приложения)

В GUI (вкладка «Server & IGate») можно выбрать режим:

- **Binary KISS** (`kiss_tcp_server.py`, порт 8023): клиент обменивается сырыми
  KISS-фреймами, как с последовательным TNC по сети. Входящие пакеты рации
  заворачиваются `frame_kiss` и шлются всем клиентам (`broadcast`).
- **AGW (AGWPE)** (`agw_server.py`, порт 8000): совместим с Dire Wolf. 36-байтный
  заголовок: `portx(1) res(3) datakind(1) res(1) pid(1) res(1) from(10) to(10)
  len(4 LE) reserved(4)`. Обрабатывает TX `V`/`M` (UI-кадры, 1 байт числа
  диджи+по 10 байт на диджи + info), `K` (raw AX.25) и монитор `U` для RX.
- **APRS-IS** (`aprsis_server.py`, порт 14580): текстовый протокол. Логин
  `user CALL pass PASSCODE vers ... filter ...`, обязательна проверка passcode
  по алгоритму (`compute_passcode`), неавторизованные — read-only, строки `#`
  не уходят в радио. Входящий от клиента текст кодируется в AX.25 и уходит в
  рацию.

### 2.8 IGate (радио ⇄ APRS-IS) и settings.json

`igate.py` — самостоятельный IGate-модуль:

- **Сеть → радио (правило a)** (`_should_gate_to_radio`): пакет гейтится в рацию,
  только если:
  1. позывной `<IGATE_NAME>` присутствует в пути (`path`), и
  2. не содержит `qAR`/`qAO` (если соответствующие флаги `check_no_qar`/
     `check_no_qao` включены), и
  3. содержит `TCPIP` (если флаг `check_tcpip` включён).
  Не прошедшие — логируются как `net --skip-> radio`.
- **Радио → сеть (правило b)** (`radio_rx`): к пути добавляется `,qAR,<IGATE_NAME>`.

Логин IGate-клиента:

```
user <APRSIS_CLIENT> pass <PASSCODE> vers TDH9KissIGate v1.0 filter <FILTER>
```

Фильтр по умолчанию — `d/<IGATE_NAME>*` (по адресату, без SSID). Если в пункте
`Filter` не задан фильтр — подставляется `d/<без SSID>*` (например для
`DKXCE-11` → `d/DKXCE*`).

**Live-применение настроек:** каждый пакет читает актуальные флаги через
`settings_getter` (`_igate_live_settings`), поэтому переключение чекбоксов
(Require TCPIP / Reject qAR / Reject qAO) применяется мгновенно, без перезапуска.

**`settings.json`** хранится в папке модуля `tidradio_kiss/settings.json`. Содержит
`aprsis_client`, `igate_name`, `passcode`, `server`, `port`, `filter`, `enabled`,
`check_tcpip`, `check_no_qar`, `check_no_qao`. Сохраняется автоматически при
нажатии **Start** и при закрытии окна (кнопки Save больше нет).

Пример:

```json
{
  "aprsis_client": "DKXCE-10",
  "igate_name": "DKXCE-11",
  "passcode": 10986,
  "server": "localhost",
  "port": 12012,
  "filter": "d/DKXCE*",
  "enabled": true,
  "check_tcpip": false,
  "check_no_qar": true,
  "check_no_qao": false
}
```

**GUI IGate:** одна кнопка **Start/Stop** (toggle), без отдельной Stop и Save.
При старте применяются и сохраняются текущие значения формы. Лог IGate пишется
в общее окно `RX/TX Log`.

### 2.9 Интерфейс (GUI)

- `main.py` строит `ttk.Notebook` с двумя вкладками:
  - вкладка **«TNC & TX»** — выбор устройства (Scan/Connect/Disconnect,
    история), статус, блок Transmit (From/To/Comment + Send + Raw-фрейм);
  - вкладка **«Server & IGate»** — сервер (Port/Mode/Start/Presets, список
    клиентов) и форма IGate (APRSIS_CLIENT / IGATE_NAME / Passcode / Server /
    Port / Filter / флаги / Start-Stop);
  - внизу, под вкладками — общее окно **«RX/TX Log»** (выделение+копирование
    Ctrl+C, кнопка Clear).

Всё логирование (`[RX]`, `[TCP <- client]`, `[IGate ...]`, `[BLE]`) идёт в это
окно.

---

## 4. Итоговая схема потока данных

```
                ┌─────────────────────────────────────────────┐
                │  TIDRadio TD-H9  (встроенный TNC + AFSK)     │
                │            эфир 1200 бод ⇄ AX.25             │
                └──────────────────────┬──────────────────────┘
                     BLE GATT service 0000af00
                TX write af01  │  RX notify af02 (KISS)
                ┌──────────────▼──────────────┐
                │        ble_radio (bleak)     │
                │   asyncio-loop в потоке      │
                └──────────────┬──────────────┘
                 send_raw(kiss)││on_rx(kiss bytes)
             ┌─────────────────▼│──────────────────┐
             │               kiss.py               │
             │  frame_kiss (FEND+FEND) / KISSParser│
             └─────────────────┬──────────────────┘
             ┌─────────────────▼──────────────────────────────┐
             │                     main.py                    │
             │  ax25.encode/decode → to_aprs_text             │
             └───────────┬──────────┬───────────┬─────────────┘
        KISS TCP 8023    │ AGW 8000 │ APRS-IS   │  IGate (radio⇄APRS-IS)
        (клиент KISS)    │ (YaAC…)  │ 14580     │  net⇄radio rules a/b
        └────────────────┴────┬─────┴─────┬─────┘
                    внешние APRS-приложения / APRS-IS сеть
```

---

## 5. Ключевые константы одной таблицей

| Параметр | Значение |
|---|---|
| SPP UUID (классика, в APK) | `00001101-0000-1000-8000-00805F9B34FB` |
| APRS BLE service | `0000af00-0000-1000-8000-00805f9b34fb` |
| APRS BLE write (TX) | `0000af01-0000-1000-8000-00805f9b34fb` |
| APRS BLE notify (RX) | `0000af02-0000-1000-8000-00805f9b34fb` |
| Fallback write | `0000af01`, `0000ff02`, `0000ffe2` |
| Fallback notify | `0000af02`, `0000ff01`, `0000ffe1` |
| Общий (не APRS) service (APK) | `0000ff00-...` |
| KISS FEND | `0xC0` |
| KISS CMD_DATA | `0x00` |
| KISS FESC / TFEND / TFESC | `0xDB` / `0xDC` / `0xDD` |
| Классы команд KISS | `0x01 TXDELAY, 0x02 PERSIST, 0x03 SLOTTIME, 0x04 TXTAIL, 0x05 FULLDUPLEX, 0x06 SETHARDWARE, 0xFF RETURN` |
| AX.25 UI control / PID | `0x03` / `0xF0` |
| Порты TCP-серверов | KISS 8023 · AGW 8000 · APRS-IS 14580 |
| IGate-клиент | APRS-IS (default `d/<IGATE_NAME>*`), settings.json в папке модуля |

---
