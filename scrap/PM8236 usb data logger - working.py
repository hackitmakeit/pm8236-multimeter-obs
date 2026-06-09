import serial
import time
import sys

def set_interface_attribs(port, baudrate=2400):
    return serial.Serial(port, baudrate=baudrate, timeout=0.5)

def prtime():
    #print(time.strftime("%c"))
    print("")
    sys.stdout.flush()

def decode_digit(raw_digit):
    digit_pattern = [0x00, 0x5f, 0x06, 0x6b, 0x2f, 0x36, 0x3d, 0x7d, 0x07, 0x7f, 0x3f, 0x58]
    digit_string = ["", "0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "L"]
    if raw_digit & 0x80:
        print(".", end="")
    for i in range(len(digit_pattern)):
        if digit_pattern[i] == (raw_digit & 0x7f):
            print(digit_string[i], end="")

def decode_bits(bits, icons):
    for i in range(8):
        if bits & 1:
            print(icons[i], end="")
        bits >>= 1

def decode_msg(raw_msg):
    if raw_msg[10] & 0x18:
        print("-", end="")
    for i in range(9, 5, -1):
        decode_digit(raw_msg[i])
    print(" ", end="")
    decode_bits(raw_msg[20], ["DegC ", "DegF ", "?", "?", "m", "u", "n", "F "])
    decode_bits(raw_msg[21], ["u", "m", "A ", "V ", "M", "k", "Ohms ", "Hz "])
    decode_bits(raw_msg[10] & 0xE7, ["Diode ", "AC ", "DC ", "-", "-", "", "Continuity ", "LowBattery "])
    decode_bits(raw_msg[18], ["", "", "", "", "Wait ", "Auto ", "Hold ", "REL "])
    decode_bits(raw_msg[19], ["", "MAX", "-", "MIN", "N/A", "%", "hFE", "N/A"])
    prtime()

def main():
    portname = "/dev/cu.usbserial-10"
    print("Data Logging interface for PeakMeter MS8236 USB Multimeter.")
    print("If logging does not start make sure USB lead is connected,")
    print("then press and hold USB button on meter for two seconds.")

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
