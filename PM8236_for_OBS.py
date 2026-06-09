import serial
import time
import sys
import io
import contextlib
import threading
import json
import logging
import os
import argparse

from serial.tools import list_ports
from flask import Flask, Response, render_template_string, stream_with_context

# Defaults — overridable via CLI flags or env vars (see parse_args()).
portname = os.environ.get("PM8236_PORT", "/dev/cu.usbserial-10")
server_port = int(os.environ.get("PM8236_HTTP_PORT", "8000"))


def set_interface_attribs(port, baudrate=2400):
    return serial.Serial(port, baudrate=baudrate, timeout=0.5)


def find_port(preferred):
    """Return a usable serial port name.

    Prefers `preferred` if it's currently present. Otherwise auto-detects a
    likely USB-serial adapter (the meter shows up as a usbserial device).
    Returns None if nothing suitable is connected.
    """
    ports = list(list_ports.comports())
    names = [p.device for p in ports]

    if preferred in names:
        return preferred

    # Auto-detect: prefer usbserial-style adapters, skip Bluetooth/debug ports.
    def looks_like_meter(name):
        n = name.lower()
        return "usbserial" in n or "usbmodem" in n or "wchusbserial" in n

    candidates = [n for n in names if looks_like_meter(n)]
    if candidates:
        return candidates[0]
    return None

def prtime():
    #print(time.strftime("%c"))
    print("")
    sys.stdout.flush()

def decode_digit(raw_digit) -> str:
    digit_pattern = [0x00, 0x5f, 0x06, 0x6b, 0x2f, 0x36, 0x3d, 0x7d, 0x07, 0x7f, 0x3f, 0x58]
    digit_string = ["", "0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "L"]
    s = ""
    if raw_digit & 0x80:
        s += "."
    for i in range(len(digit_pattern)):
        if digit_pattern[i] == (raw_digit & 0x7f):
            s += digit_string[i]
            break
    return s

def decode_bits(bits, icons) -> str:
    s = ""
    for i in range(8):
        if bits & 1:
            s += icons[i]
        bits >>= 1
    return s

# Simple in-memory publish for server -> keep latest message and notify clients
_latest_msg = [""]
_latest_cond = threading.Condition()


def publish(json_payload):
    """Store the latest payload and wake up any connected SSE clients."""
    with _latest_cond:
        _latest_msg[0] = json_payload
        _latest_cond.notify_all()


def publish_status(text):
    """Publish a status line (e.g. 'waiting for meter') to the web UI."""
    publish(json.dumps({"value": "", "units": "", "modes": "", "raw": text}))

def decode_msg(raw_msg):
    # Build structured fields
    sign = "-" if (raw_msg[10] & 0x18) else ""
    digits = "".join(decode_digit(raw_msg[i]) for i in range(9, 5, -1))
    units = decode_bits(raw_msg[20], ["DegC ", "DegF ", "?", "?", "m", "u", "n", "F "]) \
            + decode_bits(raw_msg[21], ["u", "m", "A ", "V ", "M", "k", "Ohms ", "Hz "])
    modes = decode_bits(raw_msg[10] & 0xE7, ["Diode ", "AC ", "DC ", "-", "-", "", "Continuity ", "LowBattery "]) \
            + decode_bits(raw_msg[18], ["", "", "", "", "Wait ", "Auto ", "Hold ", "REL "]) \
            + decode_bits(raw_msg[19], ["", "MAX", "-", "MIN", "N/A", "%", "hFE", "N/A"])

    # create a printable single-line text for console (preserve original behaviour)
    # build message_text explicitly (previously redirected stdout was used)
    message_text = f"{sign}{digits} {units}{modes} "

    # also publish structured JSON for the web UI
    payload = {
        "value": sign + digits,
        "units": units.strip(),
        "modes": modes.strip(),
        "raw": message_text.strip()
    }
    json_payload = json.dumps(payload)

    # keep original console behavior
    print(message_text, end="")

    # publish to web clients (send JSON string)
    publish(json_payload)

# Flask-based web UI
app = Flask(__name__)

log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

INDEX_HTML = """<!doctype html>
<html>
  <head><meta charset="utf-8"><title>MS8236 Live</title></head>
  <body>
    <table border="0" style="font-family:verdana;">
      <tr style="height:15px;">        
        <td rowspan="2" id="value" style="padding-left:7px; padding-right:7px; text-align: center; font-size:36px; background: rgba(250, 250, 250, 0.5)"></td>
        <td id="units" style="padding:1px; font-size:20px; background-color: #D7EEFF"></td>
      </tr>
      <tr style="height:15px;">
        <td id="modes" style="padding:2px; font-size:20px; background-color: #D7EEFF"></td>
      </tr>
    </table>
    <pre id="raw" style="white-space:pre-wrap; font-family:monospace; margin-top:12px;"></pre>
    <script>
      const evt = new EventSource('/events');
      const valueCell = document.getElementById('value');
      const unitsCell = document.getElementById('units');
      const modesCell = document.getElementById('modes');
      const raw = document.getElementById('raw');

      evt.onmessage = function(e) {
        try {
          const obj = JSON.parse(e.data);
          // When there's no live reading, show the status text in the big cell.
          valueCell.textContent = obj.value || obj.raw || "";
          unitsCell.textContent = obj.units || "";
          modesCell.textContent = obj.modes || "";
          raw.textContent = obj.value ? (obj.raw || "") : "";
        } catch (err) {
          raw.textContent = e.data;
        }
      };
      evt.onerror = function() {
        raw.textContent = "[Connection lost]";
        valueCell.textContent = "[Connection lost]";
        evt.close();
      };
    </script>
  </body>
</html>
"""

@app.route("/")
@app.route("/index")
def index():
    return render_template_string(INDEX_HTML)

def event_stream():
    # generator for Server-Sent Events
    try:
        # Send the current state immediately so a newly-connected client
        # (e.g. an OBS browser source) isn't blank until the next update.
        with _latest_cond:
            current = _latest_msg[0]
        if current:
            yield f"data: {current}\n\n"

        while True:
            with _latest_cond:
                _latest_cond.wait()
                msg = _latest_msg[0]
            # msg is a JSON string (single line) — send as one data: block
            yield f"data: {msg}\n\n"
    except GeneratorExit:
        # client disconnected
        return

@app.route("/events")
def sse_events():
    headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive"
    }
    return Response(stream_with_context(event_stream()), mimetype="text/event-stream", headers=headers)

def run_flask_server(host="0.0.0.0", port=8000):
    # run Flask in a background thread (disable reloader)
    app.run(host=host, port=port, threaded=True, use_reloader=False)

def read_loop(ser):
    """Read and decode messages until the serial connection drops."""
    raw_msg = bytearray(80)
    msg_index = 0

    while True:
        buf = ser.read(80)
        for b in buf:
            if b == 0xAA:
                msg_index = 0
            raw_msg[msg_index] = b
            msg_index += 1
            if msg_index >= 80:
                msg_index = 79
            if msg_index == 22:
                decode_msg(raw_msg)
                msg_index = 0


def parse_args():
    p = argparse.ArgumentParser(
        description="Live PeakMeter PM8236/MS8236 USB multimeter readout for OBS."
    )
    p.add_argument("-p", "--port", default=portname,
                   help=f"serial port of the meter (default: {portname}; "
                        "auto-detects a usbserial adapter if this isn't present)")
    p.add_argument("-P", "--http-port", type=int, default=server_port,
                   help=f"port for the web UI (default: {server_port})")
    p.add_argument("--list-ports", action="store_true",
                   help="list available serial ports and exit")
    return p.parse_args()


def main():
    # print("Data Logging interface for PeakMeter MS8236 USB Multimeter.")
    # print("If logging does not start make sure USB lead is connected,")
    # print("then press and hold USB button on meter for two seconds.")

    args = parse_args()

    if args.list_ports:
        ports = list(list_ports.comports())
        if not ports:
            print("No serial ports found.")
        else:
            print("Available serial ports:")
            for p in ports:
                print(f"  {p.device}  -  {p.description}")
        return

    # start Flask web server
    try:
        t = threading.Thread(target=run_flask_server,
                             kwargs={"host": "0.0.0.0", "port": args.http_port},
                             daemon=True)
        t.start()
        print(f"Web UI started at http://localhost:{args.http_port}/")
    except Exception as e:
        print(f"Failed to start web server: {e}")

    print("Waiting for meter — connect USB and hold the meter's USB button for ~2s.")
    print("Press Ctrl+C to quit.")

    # Reconnect loop: tolerate the meter being absent or unplugged at any time.
    announced_waiting = False
    try:
        while True:
            port = find_port(args.port)
            if port is None:
                if not announced_waiting:
                    publish_status("Waiting for meter…")
                    announced_waiting = True
                time.sleep(1.0)
                continue

            try:
                ser = set_interface_attribs(port)
            except serial.SerialException as e:
                print(f"Error opening {port}: {e}")
                publish_status(f"Cannot open {port} — retrying…")
                announced_waiting = False
                time.sleep(2.0)
                continue

            print(f"\nConnected to meter on {port}.")
            announced_waiting = False
            try:
                read_loop(ser)
            except serial.SerialException as e:
                print(f"\nSerial connection lost ({e}); will retry…")
                publish_status("Meter disconnected — retrying…")
            finally:
                try:
                    ser.close()
                except Exception:
                    pass
            time.sleep(1.0)
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
