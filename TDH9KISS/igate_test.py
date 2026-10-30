"""
==============================================================================
  IGate client test / mock script (APRS-IS outbound)
  Author:  dkxce (c)  https://github.com/dkxce/Tidradio-TD-H9
  Version: v1.1.0.0

  Russian:  Тестовый скрипт IGate-клиента. Подключается к APRS-IS серверу
            (локальному или удалённому), логинится как пользователь
            APRS-IS и циклично отправляет сформированный APRS-пакет с
            имитацией IGate (q-конструкт qAR,IGATE_NAME). Подходит для
            проверки серверов dkxce/SimpleAPRSServer и встроенного APRS-IS.
  English:  Test IGate client. Connects to an APRS-IS server (local or
            remote), logs in as an APRS-IS user and repeatedly sends a
            generated APRS packet with an IGate simulation (q-construct
            qAR,IGATE_NAME). Usable against dkxce/SimpleAPRSServer and the
            built-in APRS-IS mode.
==============================================================================
"""

import socket
import sys
import time

__author__ = "dkxce (c) https://github.com/dkxce/Tidradio-TD-H9"
__version__ = "v1.1.0.0"

# --- Connection settings / настройки подключения ---
CALLSIGN        = "N0CALL-9"
PASSCODE        = "13023"
SERVER_HOST     = "localhost"
SERVER_PORT     = 12012
SEND_BEACON     = False

# --- Message settings / настройки сообщения ---
TARGET_CALLSIGN = "NONAME"
MESSAGE_TEXT    = "Hello from Python APRS-IS mock script!"
IGATE_NAME      = "DKXCE-11"




def create_aprs_message_packet(source, destination, message, igate):
    """Build a valid APRS message packet (U-frame) for the APRS-IS stream.

    To imitate an IGate, the q-construct ',qAR,<IGATE_NAME>' is appended to
    the path so receiving software treats the packet as gated.

    Russian:  Собирает валидный APRS-пакет для потока APRS-IS. Для имитации
              IGate в путь добавляется q-конструкт ',qAR,<IGATE_NAME>'.
    """
    padded_destination = f"{destination:<9}"    
    if SEND_BEACON:
        packet = f"{source}>APRS,TCPIP*,{igate}:!4435.00N/04006.00-000/000/A=000001\r\n"
    else:
        packet = f"{source}>APRS,TCPIP*,{igate}::{padded_destination}:{message}\r\n"
    return packet


def main():
    login_line = f"user {CALLSIGN} pass {PASSCODE} vers MockPythonScript 1.0\r\n"
    aprs_packet = create_aprs_message_packet(
        CALLSIGN, TARGET_CALLSIGN, MESSAGE_TEXT, IGATE_NAME)

    print(f"[*] Built packet: {aprs_packet.strip()}")
    print(f"[*] Connecting to {SERVER_HOST}:{SERVER_PORT}...")

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(10)
            s.connect((SERVER_HOST, SERVER_PORT))

            # Read the server welcome banner.
            server_welcome = s.recv(1024).decode("ascii", errors="ignore")
            print(f"[<] Server response: {server_welcome.strip()}")

            # Send the login/authorization line.
            s.sendall(login_line.encode("ascii"))
            print(f"[>] Sent authorization: {login_line.strip()}")

            # Read the login confirmation.
            auth_response = s.recv(1024).decode("ascii", errors="ignore")
            print(f"[<] Server response: {auth_response.strip()}")

            while True:
                print("[*] Pausing 1 second before sending the APRS packet...")
                time.sleep(1.0)

                p = aprs_packet.encode("ascii")
                s.sendall(p)
                print(f"[>] Packet sent: {p.strip()}")

                time.sleep(5)

    except socket.timeout:
        print("[!] Error: timed out waiting for a server response.")
    except Exception as e:
        print(f"[!] Error while sending: {e}")


if __name__ == "__main__":
    main()