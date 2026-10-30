"""
==============================================================================
  Human-readable descriptions for BLE GATT services / characteristics
  Author:  dkxce (c)  https://github.com/dkxce/Tidradio-TD-H9
  Version: v1.1.0.0

  Russian:  Человекочитаемые описания BLE GATT-сервисов/характеристик.
  English:  Human-readable descriptions for BLE GATT services/characteristics.

  Used to enrich the per-device config file ``devcfg_<address>.json`` with a
  ``description`` field that explains what a service/characteristic is, what it
  is used for and whether / how this program uses it.

  The UUID-to-name mapping covers the common TIDRadio / Odmaster BLE services
  plus the standard Bluetooth SIG services.
==============================================================================
"""

from __future__ import annotations

__author__ = "dkxce (c) https://github.com/dkxce/Tidradio-TD-H9"
__version__ = "v1.1.0.0"

# Service uuid (lower 16-bit, without the 0000-1000-8000-00805f9b34fb suffix) -> info
SERVICE_INFO: dict = {
    "1800": {"name": "Generic Access",
             "what": "Standard access-level service (device name, appearance, device characteristics).",
             "used": False},
    "af00": {"name": "APRS / KISS TNC (Odmaster)",
             "what": "Service from the Odmaster app for exchanging KISS/AX.25 frames with the APRS radio. Used by this program to send and receive APRS packets.",
             "used": True},
    "ff00": {"name": "TIDRadio command / programming",
             "what": "Radio configuration and command service (frequency programming, handshake, DX commands). Used by the Odmaster app to configure the radio.",
             "used": False},
    "ae00": {"name": "OTA / firmware (JL OTA)",
             "what": "Firmware update service (JL/Jieli OTA). Used to flash new firmware into the radio.",
             "used": False},
    "ae30": {"name": "OTA / firmware (JL OTA, alt)",
             "what": "Alternative firmware update service (JL/Jieli OTA).",
             "used": False},
}

CHARACTERISTIC_INFO: dict = {
    ("af00", "af01"): {"name": "APRS TX (write)",
                       "what": "Channel for writing a KISS frame into the radio (write-without-response).",
                       "used": True, "how": "The program writes KISS frames (FEND+AX25+FEND) here to transmit APRS over the air."},
    ("af00", "af02"): {"name": "APRS RX (notify)",
                       "what": "Channel for receiving KISS frames from the radio (notify).",
                       "used": True, "how": "The program subscribes to notify and decodes incoming AX.25 frames into APRS packets."},
    ("ff00", "ff01"): {"name": "Command notify", "what": "Notifications of radio commands/responses.",
                       "used": False},
    ("ff00", "ff02"): {"name": "Command write", "what": "Writing radio configuration commands.",
                       "used": False},
    ("ff00", "ff21"): {"name": "Command notify (DX)", "what": "Notifications of extended commands.",
                       "used": False},
    ("ff00", "ff22"): {"name": "Command write (DX)", "what": "Writing extended commands.",
                       "used": False},
    ("ae00", "ae01"): {"name": "OTA data (write)", "what": "Uploading firmware data.",
                       "used": False},
    ("ae00", "ae02"): {"name": "OTA notify", "what": "Notifications about firmware progress/responses.",
                       "used": False},
    ("ae30", "ae01"): {"name": "OTA data (write, alt)", "what": "Uploading firmware data (alternative service).",
                       "used": False},
    ("ae30", "ae02"): {"name": "OTA notify (alt)", "what": "Notifications about firmware progress/responses (alternative service).",
                       "used": False},
    ("1800", "2a00"): {"name": "Device Name", "what": "BLE device name.",
                       "used": False},
}


def _svc_key(uuid_lower: str) -> str:
    """Return the key used to look up a service.

    Russian:  Возвращает ключ для поиска сервиса.
    English:  Returns the lookup key for a service.
    """
    return uuid_lower.lower()


def _char_key(svc_uuid: str, char_uuid: str) -> tuple:
    # Russian: ключ (сервис, характеристика) в короткой 16-битной форме.
    # English: (service, characteristic) lookup key in short 16-bit form.
    return (_short(svc_uuid), _short(char_uuid))


def _short(uuid: str) -> str:
    """Reduce a 128-bit UUID with the standard base to its 16-bit form.

    '0000af00-0000-1000-8000-00805f9b34fb' -> 'af00'
    '00001800-...' -> '1800'
    Other UUIDs are returned unchanged (lowercased).

    Russian:  Сокращает стандартный 128-битный UUID до 16-битной формы.
    English:  Reduces a standard 128-bit UUID to 16-bit form.
    """
    u = str(uuid).lower()
    if u.endswith("-0000-1000-8000-00805f9b34fb") and u.startswith("0000") and len(u) == 36:
        return u[4:8]
    return u


def service_description(svc_uuid: str) -> str:
    """Return a text description for a service UUID (in English).

    Russian:  Возвращает текстовое описание для UUID сервиса.
    English:  Returns a textual description for a service UUID.
    """
    k = _short(svc_uuid)
    info = SERVICE_INFO.get(k)
    if info is None:
        return f"Unknown service {svc_uuid}. Purpose not determined."
    used = "Used by the program." if info["used"] else "Not used by the program."
    return f"{info['name']} - {info['what']} ({used})"


def characteristic_record(svc_uuid: str, char_uuid: str, handle: int,
                          props: list, is_aprs_best_match: bool = False) -> dict:
    """Build one characteristic record enriched with a description.

    Russian:  Собирает запись характеристики с описанием (EN).
    English:  Builds one characteristic record with an English description.
    """
    key = _char_key(svc_uuid, char_uuid)
    info = CHARACTERISTIC_INFO.get(key, {})
    name = info.get("name", "")
    what = info.get("what", "")
    used = info.get("used", False)
    how = info.get("how", "")

    parts = []
    if name:
        parts.append(name)
    if what:
        parts.append(what)
    if used:
        parts.append("Used by the program.")
        if how:
            parts.append(how)
    else:
        parts.append("Not used by the program.")
    # Mark as used if it is a best-match write/notify candidate.
    # Russian: отмечаем как используемый, если это подходящий write/notify канал.
    used_flag = bool(used) or is_aprs_best_match

    description = " ".join(parts)

    return {
        "service": svc_uuid,
        "characteristic": char_uuid,
        "handle": handle,
        "properties": sorted(props),
        "used_in_app": used_flag,
        "description": description,
    }