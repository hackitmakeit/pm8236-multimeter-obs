# PM8236 multimeter readout for OBS

Live readout for a **PeakMeter PM8236 / MS8236** USB multimeter. It reads the
meter over its USB-serial link, decodes the display protocol, and serves a small
web page you can drop into [OBS](https://obsproject.com/) as a **Browser Source**
to overlay the live measurement on a stream or recording.

The same page works in any browser if you just want a big on-screen readout.

## How it works

```
PM8236 meter  ──USB serial──▶  PM8236_for_OBS.py  ──HTTP (SSE)──▶  browser / OBS
```

The script reads raw frames from the serial port, decodes them into a value,
units, and mode flags, and pushes updates to connected browsers over
Server-Sent Events so the overlay updates in real time.

## Requirements

- Python 3.8+
- [`pyserial`](https://pypi.org/project/pyserial/) and [`Flask`](https://pypi.org/project/Flask/)

```bash
pip install pyserial flask
```

## Usage

1. Connect the meter by USB and **press and hold its USB button for ~2 seconds**
   to put it into data-output mode.
2. Run the script:

   ```bash
   python PM8236_for_OBS.py
   ```

3. Open <http://localhost:8000/> in a browser, or add it as a Browser Source in OBS.

The script auto-detects a USB-serial adapter, so it usually just works. If you
have several serial devices, list them and pick one explicitly:

```bash
python PM8236_for_OBS.py --list-ports
python PM8236_for_OBS.py --port /dev/cu.usbserial-10
```

### Options

| Flag | Default | Description |
| --- | --- | --- |
| `-p`, `--port` | `/dev/cu.usbserial-10` | Serial port of the meter. Auto-detects a usbserial adapter if this one isn't present. |
| `-P`, `--http-port` | `8000` | Port for the web UI. |
| `--list-ports` | — | List available serial ports and exit. |

Both defaults can also be set via the `PM8236_PORT` and `PM8236_HTTP_PORT`
environment variables.

The script tolerates the meter being absent or unplugged — it shows a
"waiting for meter" status and reconnects automatically when the meter appears.

## Tests

The pure protocol-decoding helpers are covered by unit tests:

```bash
python -m unittest test_decode
```
