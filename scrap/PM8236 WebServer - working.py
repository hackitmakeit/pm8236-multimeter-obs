import serial
import time
import sys
import io
import contextlib
import threading
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

def set_interface_attribs(port, baudrate=2400):
    return serial.Serial(port, baudrate=baudrate, timeout=0.5)

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
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        print(sign, end="")
        print(digits, end="")
        print(" ", end="")
        print(units, end="")
        print(modes, end="")
        prtime()
    message_text = buf.getvalue()

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
    with _latest_cond:
        _latest_msg[0] = json_payload
        _latest_cond.notify_all()

def main():
    portname = "/dev/cu.usbserial-210"
    print("Data Logging interface for PeakMeter MS8236 USB Multimeter.")
    print("If logging does not start make sure USB lead is connected,")
    print("then press and hold USB button on meter for two seconds.")

    # start simple web server to stream messages via Server-Sent Events (SSE)
    def make_handler():
        class SSEHandler(BaseHTTPRequestHandler):
            def log_message(self, format, *args):
                # silence access logs
                return

            def do_GET(self):
                if self.path == "/" or self.path.startswith("/index"):
                    content = """<!doctype html>
<html>
  <head><meta charset="utf-8"><title>MS8236 Live</title></head>
  <body>
    <h2>MS8236 Live Readout</h2>
    <table border="1" style="font-family:monospace;">
      <tr><th>Value</th><th>Units</th><th>Modes</th></tr>
      <tr>
        <td id="value" style="padding:8px;"></td>
        <td id="units" style="padding:8px;"></td>
        <td id="modes" style="padding:8px;"></td>
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
          valueCell.textContent = obj.value || "";
          unitsCell.textContent = obj.units || "";
          modesCell.textContent = obj.modes || "";
          raw.textContent = obj.raw || "";
        } catch (err) {
          // fallback: show raw text
          raw.textContent = e.data;
        }
      };
      evt.onerror = function() {
        raw.textContent = "[Connection lost]";
        evt.close();
      };
    </script>
  </body>
</html>"""
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(content.encode("utf-8"))))
                    self.end_headers()
                    self.wfile.write(content.encode("utf-8"))
                    return

                if self.path == "/events":
                    self.send_response(200)
                    self.send_header("Content-Type", "text/event-stream")
                    self.send_header("Cache-Control", "no-cache")
                    self.send_header("Connection", "keep-alive")
                    self.end_headers()
                    # send initial comment to keep connection
                    try:
                        while True:
                            with _latest_cond:
                                _latest_cond.wait()
                                msg = _latest_msg[0]
                            # send SSE 'data' line(s)
                            for ln in msg.splitlines():
                                data_line = f"data: {ln}\n"
                                self.wfile.write(data_line.encode("utf-8"))
                            self.wfile.write(b"\n")
                            self.wfile.flush()
                    except (BrokenPipeError, ConnectionResetError):
                        return

                # not found
                self.send_response(404)
                self.end_headers()
        return SSEHandler

    server_port = 8000
    try:
        httpd = ThreadingHTTPServer(("0.0.0.0", server_port), make_handler())
        t = threading.Thread(target=httpd.serve_forever, daemon=True)
        t.start()
        print(f"Web UI started at http://localhost:{server_port}/")
    except Exception as e:
        print(f"Failed to start web server: {e}")

    try:
        ser = set_interface_attribs(portname)
    except serial.SerialException as e:
        print(f"Error opening {portname}: {e}")
        return

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

if __name__ == "__main__":
    main()
