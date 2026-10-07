# Описание GNSS-конфигурации в `.td` файле

> [Основное описание](README.md)

Блок GNSS располагается в EEPROM-образе `.td` по адресу **`0x3066`** и занимает **22 байта** (до `0x307B`).     
Сразу после него (`0x307C`) начинается блок [APRS](aprs.md).    

```
0x3066 .. 0x306B  : параметры GNSS-модуля
0x306C .. 0x3079  : фиксированная позиция (Lon/Lat/Alt + полушария)
0x307A .. 0x307B  : резерв + тип станции GNSS
```

## Полная таблица блока GNSS (0x3066..0x307B)

| Смещение | Длина | Тип | Поле | Значения |
|---|---|---|---|---|
| `0x3066` | 1 | bit | **GPS On/Off** | 0 – Off, 1 – On |
| `0x3067` | 1 | uint8 | **GPS Position Type** | 0 – Deg, 1 – Deg.min, 2 – Deg.min.sec |
| `0x3068` | 1 | uint8 | **GPS Time Zone** | 0 (UTC−12) … 24 (UTC+12) |
| `0x3069` | 1 | uint8 | **Speed Unit** | 0 – Km/h, 1 – Knot, 2 – m/s |
| `0x306A` | 1 | uint8 | **Dist Unit** | 0 – Km/h, 1 – Sea mile, 2 – Mile |
| `0x306B` | 1 | uint8 | **Alt Unit** | 0 – Meters, 1 – Feet |
| `0x306C` | 4 | BE u32 | **Fixed Longitude** | градусы × 1e-6 |
| `0x3070` | 1 | ASCII | **Fixed Longitude E/W** | `E` / `W` |
| `0x3071` | 4 | BE u32 | **Fixed Latitude** | градусы × 1e-6 |
| `0x3075` | 1 | ASCII | **Fixed Latitude N/S** | `N` / `S` |
| `0x3076` | 4 | BE i32 | **Fixed Altitude** | метры × 1e-6 (знаковое) |
| `0x307A` | 1 | — | **RESERVED** | — |
| `0x307B` | 1 | uint8 | **GNSS-station type** | 0 – Fix, 1 – GPS |

## Правила

- **Lon / Lat** — беззнаковые 32-битные **big-endian**, единица — **×1e-6** градуса (`градусы = raw / 1e6`).
- **Alt** — знаковое 32-битное **big-endian** (two's complement), единица — **×1e-6** метра (`метры = raw / 1e6`).
- **Полушария** — отдельные ASCII-байты: долгота `E`/`W`, широта `N`/`S`.

## Пример: Сочи (43.5855°N, 39.7233°E, alt 10 м)

Байты координат:

```
Lon = round(39.7233×1e6) = 39723300 = 0x025E2124
Lat = round(43.5855×1e6) = 43585500 = 0x02990FDC
Alt = round(10×1e6)      = 10000000 = 0x00989680
```

Собранный блок (позиция):

```
0x306C  02 5E 21 24 | 45 | 02 99 0F DC | 4E | 00 98 96 80
        Lon=39.7233   E    Lat=43.5855   N     Alt=+10 м
```

Проверка (python):

```python
rec = bytes.fromhex('025e21244502990fdc4e00989680')
lon = int.from_bytes(rec[0:4],'big')/1e6     # 39.7233
e_w = chr(rec[4])                            # 'E'
lat = int.from_bytes(rec[5:9],'big')/1e6     # 43.5855
n_s = chr(rec[9])                            # 'N'
alt = int.from_bytes(rec[10:14],'big',signed=True)/1e6  # 10.0
```
