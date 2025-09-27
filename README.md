ESPLinky
A custom Home Assistant integration designed to receive and parse Tele-Information Client (TIC) frames from a Linky smart meter via a UDP socket, primarily using an ESP-based device (e.g., ESP8266 or ESP32).

Features
Listens for raw Linky TIC frames pushed over UDP (default port: 8095).

Parses frames in Historic Mode.

Validates the checksum for every single data line to ensure data integrity.

Dynamically creates Home Assistant sensor entities for all valid Linky labels (e.g., BASE, PAPP, IINST).

Installation
Install this repository as a Custom Repository in HACS.

Restart Home Assistant.

Go to Settings -> Devices & Services -> Add Integration and search for "Esplinky TIC UDP Listener".

Configure the UDP port (default is 8095).

Dependencies
This integration requires a separate device (like an ESP32) connected to the Linky TIC port configured to send the raw serial data over UDP to your Home Assistant machine on the configured port.
