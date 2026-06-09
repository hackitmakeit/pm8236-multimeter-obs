import serial
import time
import sys

def set_interface_attribs(ser, speed):
    ser.baudrate = speed
    ser.bytesize = serial.EIGHTBITS
    ser.parity = serial.PARITY_NONE
    ser.stopbits = serial.STOPBITS_ONE
    ser.xonxoff = False
    ser.rtscts = False
    ser.dsrdtr = False
    ser.timeout = 1  # Non-blocking read with 1-second timeout
    return ser

def prtime():
    current_time = time.time()
    if current_time == -1:
        print("Failure to obtain the current time.", file=sys.stderr)
        sys.exit(1)
    c_time_string = time.ctime(current_time)
    if not c_time_string:
        print("Failure to convert the current time.", file=sys.stderr)
        sys.exit(1)
    print(c_time_string, end="")

def decode_digit(raw_digit):
    
    digit_pattern = [0x00, 0x5F, 0x06, 0x6B, 0x2F, 0x36, 0x3D, 0x7D, 0x07, 0x7F, 0x3F, 0x58]
    digit_string = ["", "0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "L"]
    
    if raw_digit & 0x80:
        print(".", end="")
    for i in range(12):
        if digit_pattern[i] == (raw_digit & 0x7F):
            print(digit_string[i], end="")



def decode_bits(bits, icon):
    for i in range(8):
        if bits & 1:
            print(icon[i], end="")
        bits = bits >> 1

def decode_msg(raw_msg):
    
    if raw_msg[10] & 0x18:
        print("-", end="")
    
    decode_digit(raw_msg[9])
    decode_digit(raw_msg[8])
    decode_digit(raw_msg[7])
    decode_digit(raw_msg[6])
    print(" ", end="")
    
    icons20 = ["DegC ", "DegF ", "?", "?", "m", "u", "n", "F "]
    decode_bits(raw_msg[20], icons20)
    
    icons21 = ["u", "m", "A ", "V ", "M", "k", "Ohms ", "Hz "]
    decode_bits(raw_msg[21], icons21)
    
    icons10 = ["Diode ", "AC ", "DC ", "-", "-", "", "Continuity ", "LowBattery "]
    decode_bits(raw_msg[10] & 0xE7, icons10)
    
    icons18 = ["", "", "", "", "Wait ", "Auto ", "Hold ", "REL "]
    decode_bits(raw_msg[18], icons18)
    
    icons19 = ["", "MAX", "-", "MIN", "N/A", "%", "hFE", "N/A"]
    decode_bits(raw_msg[19], icons19)
    prtime()

def main():
    portname = "port3"
    #portname = "/dev/ttyUSB0"
    #print("Data Logging interface for PeakMeter MS8236 USB Multimeter.")
    #print("If logging does not start make sure USB lead is connected,")
    #print("then press and hold USB button on meter for two seconds.")

    try:
        ser = serial.Serial(portname)
    except serial.SerialException as e:
        print(f"Error opening {portname}: {e}")
        return -1

    set_interface_attribs(ser, 2400)

    msg_index = 0
    raw_msg = [0] * 80

    try:
        while True:
            buf = ser.read(80)
            if buf:
                for byte in buf:
                    if byte == 0xAA:
                        msg_index = 0
                    raw_msg[msg_index] = byte
                    msg_index += 1
                    if msg_index >= 80:
                        msg_index = 79
                    if msg_index == 22:
                        decode_msg(raw_msg)
                        msg_index = 0
            else:
                print("Error from read: No data received")
    except KeyboardInterrupt:
        print("Exiting program.")
    finally: 
        ser.close()

if __name__ == "__main__":
    main()