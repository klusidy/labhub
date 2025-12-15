import serial


ser = serial.Serial("COM5", 9600, timeout=1)
print(ser.readline().decode(errors="ignore").strip())
ser.write(b"CMP 1\r")
aa = ser.readline().decode(errors="ignore").strip()
aa
bool(int(aa))

ser.write(b"ACC\r")
print(ser.readline().decode(errors="ignore").strip())

# --- set ON (1) or OFF (0) ---
ser.write(b"CDO 0\r")   # turn amplifier ON
print(ser.readline().decode(errors="ignore").strip())

# --- set current in amperes (example: 4 A) ---
ser.write(b"ACC 2\r")   # set current to 4 A
print(ser.readline().decode(errors="ignore").strip())

value = True
value_int = int(value)
f"CDO {value_int}\r".encode("ascii")

ser.close()


cmd = "ACC"
aa = (cmd + "\r").encode("ascii")
print(cmd)

print(aa)
ser.reset_input_buffer()
ser.write((cmd + "\r").encode("ascii"))
ser.flush()
ser.readline().decode("ascii", errors="ignore").strip()


def _send(ser, cmd: str) -> str:
        #print(f"Sent command: {cmd}")
        ser.write((cmd + "\r").encode("ascii"))
        ser.flush()
        return ser.readline().decode("ascii", errors="ignore").strip()

aa = _send(ser, "ACC")

aa