# Описание APRS-конфигурации в `.td` файле

> [Основное описание](README.md)

Область данных APRS расположена в EEPROM-образе (`.td`) с `0x307C` по `0x3113` включительно сразу за [GNSS](gnss.md)-блоком. 
Размер блока: **152 байта** (0x307C–0x3113). Идёт сразу после GNSS-конфигурации.

Ниже таблица полей. Смещения даны в двух видах:
- **Abs** — абсолютный адрес относительно начала всего дампа (65536 байт);
- **Rel** — сдвиг относительно начала блока APRS (`0x307C`).

Оба — hex.

## Общая карта

```
0x307C                                           0x3114
  |<------------------ 152 байта ---------------->|
  | identity | резерв | beacon | иконка | путь | relay | chan |
```

> [APRS Меню](../../TD-H9_manual_ru.md#740-aprs)

| Abs | Rel | Dec | Длина | Тип | Описание |
|---|---|---|---|---|---|
| `0x307C` | `0x0000` | 12412 | 1 | bit | **APRS Switch** (0 – Off, 1 – On) |
| `0x307D` | `0x0001` | 12413 | 6 | ASCII | **Callsign** (позывной) без SSID |
| `0x3083` | `0x0007` | 12419 | 1 | uint8 | **Callsign SSID** (0–15) |
| `0x3084` | `0x0008` | 12420 | 1 | char | **Icon Table** — `/` (Primary) или `\` (Alternate) |
| `0x3085` | `0x0009` | 12421 | 16 | — | *резерв / неизвестно* |
| `0x3095` | `0x0019` | 12437 | 40 | ASCII | **Комментарий** Beacon-пакета (до 40 симв.; набор: англ. буквы, цифры, пробел, `: . , - ? ! @`) |
| `0x30BD` | `0x0041` | 12477 | 25 | — | *резерв / неизвестно* |
| `0x30D6` | `0x005A` | 12502 | 1 | uint8 | **Icon Main Symbol** — индекс 0..93 (см. [`APRS_symbols.md`](APRS_symbols.md)) |
| `0x30D7` | `0x005B` | 12503 | 1 | bit | **MIC-E Start** (0 – Off, 1 – On) |
| `0x30D8` | `0x005C` | 12504 | 1 | uint8 | **MIC-E Type** (0..7): 0 Off Duty, 1 En Route, 2 In Service, 3 Returning, 4 Committed, 5 Special, 6 Priority, 7 Emergency |
| `0x30D9` | `0x005D` | 12505 | 8 | ASCII | **Route-1: Name** (например `WIDE1`) |
| `0x30E1` | `0x0065` | 12513 | 1 | uint8 | **Route-1: Count** (SSID, напр. 1 → `WIDE1-1`) |
| `0x30E2` | `0x0066` | 12514 | 8 | ASCII | **Route-2: Name** (например `WIDE2`) |
| `0x30EA` | `0x006E` | 12522 | 1 | uint8 | **Route-2: Count** (SSID, напр. 2 → `WIDE2-2`) |
| `0x30EB` | `0x006F` | 12523 | 1 | bit | **Report Voltage** (0 – Off, 1 – On) |
| `0x30EC` | `0x0070` | 12524 | 1 | bit | **Report Sats** (0 – Off, 1 – On) |
| `0x30ED` | `0x0071` | 12525 | 1 | bit | **Report Mileage** (0 – Off, 1 – On) |
| `0x30EE` | `0x0072` | 12526 | 1 | bit | **PTT Linkage** (0 – Off, 1 – On) |
| `0x30EF` | `0x0073` | 12527 | 1 | bit | **Timed Beacon** (0 – Off, 1 – On) |
| `0x30F0` | `0x0074` | 12528 | 2 | uint16 LE | **Time Interval** (секунды) |
| `0x30F2` | `0x0076` | 12530 | 1 | uint8 | **DIGI Forward Channel** (0 – A, 1 – B, 2 – A+B) |
| `0x30F3` | `0x0077` | 12531 | 1 | bit | **DIGI1 Enabled** (0 – Off, 1 – On) |
| `0x30F4` | `0x0078` | 12532 | 8 | ASCII | **DIGI1: Name** (например `WIDE1`) |
| `0x30FC` | `0x0080` | 12540 | 1 | bit | **DIGI2 Enable** (0 – Off, 1 – On) |
| `0x30FD` | `0x0081` | 12541 | 8 | ASCII | **DIGI2: Name** (например `WIDE2`) |
| `0x3105` | `0x0089` | 12549 | 1 | uint8 | **Wait Before Forward** (0..9) |
| `0x3106` | `0x008A` | 12550 | 8 | ASCII (digits) | **Remote Password** (0–9) |
| `0x310E` | `0x0092` | 12558 | 1 | uint8 | **APRS RX Channel** (0 – Off, 1 – A, 2 – B) |
| `0x310F` | `0x0093` | 12559 | 1 | uint8 | **APRS TX Channel** (0 – A-Lock, 1 – B-Lock, 2 – A-Auto, 3 – B-Auto, 4 – A+B) |
| `0x3110` | `0x0094` | 12560 | 1 | uint8 | **APRS PTT Priority** (0 – Call, 1 – APRS) |
| `0x3111` | `0x0095` | 12561 | 2 | — | *резерв / неизвестно* |
| `0x3113` | `0x0097` | 12563 | 1 | bit | **APRS RX Auto Popup** (0 – Off, 1 – On) |

Конец блока: `0x3114` = `12564`.

## Пример реальных данных (`1.td`)

```
0x307C: 01 55 42 33 41 41 43 0B 2F 00 ...   .UB3AAC./...
0x3095: 76 6F 69 63 65 2C 61 70 72 73 20 ... "voice,aprs ..."
0x30D6: 1B                   -> Icon = 27  (Motorcycle, таблица '/')
0x30D9: 57 49 44 45 31 00 00 00 01         WIDE1...1  (Route-1 = WIDE1-1)
0x30E2: 57 49 44 45 32 00 00 00 02         WIDE2...2  (Route-2 = WIDE2-2)
```

## Пара примеров разбора

- **Путь** строится из пары `Name(8) + Count(1)`: `WIDE1` + count 1 → `WIDE1-1`, `WIDE2` + count 2 → `WIDE2-2`.
- **Иконка**: байт `0x30D6` = индекс в таблице символов (от 0). Таблица — [APRS_symbols.md](APRS_symbols.md). Итоговый символ = таблица(`/` или `\`) + символ по индексу.
- **Комментарий**: 40 байт ASCII, строка до первого `0x00`. Допустимые символы: англ. буквы, цифры, пробел, `: . , - ? ! @`.

## Примечания

- «Неизвестные» области (`0x3085–0x3094`, `0x30BD–0x30D5`, `0x3111–0x3112`) в протестированных файлах заполнены нулями — вероятно, зарезервированы.
- `Report Volt/Sats/Mile` — одиночные биты; остальные биты соответствующих байтов не трогаются.
- `Time Interval` — 16-bit little-endian.



## Пример реализации

1. [**TD-APRS-Editor**](td-editor-aprs.html) - aprs-html-редактор каналов [онлайн](https://dkxce.github.io/temporary/td-h9/td-editor-aprs.html)
