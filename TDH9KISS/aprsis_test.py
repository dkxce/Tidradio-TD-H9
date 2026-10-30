"""
==============================================================================
  APRS-IS passive listener (Receive/Receive-only client test)
  Author:  dkxce (c)  https://github.com/dkxce/Tidradio-TD-H9
  Version: v1.1.0.0

  Russian:  Тестовый слушающий APRS-IS клиент. Подключается к APRS-IS
            серверу, логинится (passcode -1 = только чтение) и выводит в
            консоль принимаемые пакеты. При обрыве соединения переподключается
            автоматически. Подходит для проверки серверов dkxce/SimpleAPRSServer
            и встроенного APRS-IS режима.
  English:  Passive APRS-IS listening client. Connects to an APRS-IS server,
            logs in (passcode -1 = receive-only) and prints received packets
            to the console, reconnecting automatically on disconnect. Usable
            against dkxce/SimpleAPRSServer and the built-in APRS-IS mode.
==============================================================================
"""

import socket
import time

__author__ = "dkxce (c) https://github.com/dkxce/Tidradio-TD-H9"
__version__ = "v1.1.0.0"

# --- Connection settings / настройки подключения ---
# rotate.aprs2.net will route you to the nearest stable server automatically.
APRS_SERVER = "localhost"
APRS_PORT = 8023

# Any callsign works (e.g. NOCALL); the -SSID suffix is optional (e.g. -10).
CALLSIGN = "NOCALL-10"
# Passcode -1 allows receive-only (read) access to APRS-IS.
PASSCODE = "-1"
APP_NAME = "SimplePythonListener 1.0"

# 'r/0/0/0' disables geographical limits and requests ALL packets worldwide.
# Beware: the data stream will be VERY dense!
# If it is too heavy, replace with 'm/500' (packets within 500 km of you).
APRS_FILTER = "r/0/0/0"


def listen_aprs():
    while True:
        try:
            print(f"Connecting to {APRS_SERVER}:{APRS_PORT}...")
            # Create a TCP socket.
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            # Set a timeout so the script does not hang if the link drops.
            s.settimeout(20)
            s.connect((APRS_SERVER, APRS_PORT))

            # Build the APRS-IS authorization line.
            auth_line = (f"user {CALLSIGN} pass {PASSCODE} "
                         f"vers {APP_NAME} filter {APRS_FILTER}\r\n")
            s.sendall(auth_line.encode('utf-8'))
            print("Authorization sent. Waiting for packets...\n" + "=" * 50)

            buffer = ""
            while True:
                # Receive a chunk of data from the socket.
                data = s.recv(4096).decode('utf-8', errors='ignore')
                if not data:
                    print("\n[!] Server closed the connection.")
                    break

                buffer += data
                # Packets in APRS are separated by line breaks (\r\n).
                while "\r\n" in buffer:
                    line, buffer = buffer.split("\r\n", 1)

                    # Skip server service comments (they start with '#').
                    if line.startswith("#"):
                        # Print the server's login success message.
                        if "loglin" in line or "verified" in line:
                            print(f"[Server]: {line}")
                        continue

                    # Print the raw APRS packet to the console.
                    if line.strip():
                        print(line)

        except socket.timeout:
            print("\n[!] Connection timeout. Reconnecting...")
        except (ConnectionRefusedError, OSError) as e:
            print(f"\n[!] Network error: {e}. Retrying in 10 seconds...")
            time.sleep(10)
        except KeyboardInterrupt:
            print("\n[!] Script stopped by the user.")
            try:
                s.close()
            except Exception:
                pass
            break


if __name__ == "__main__":
    listen_aprs()