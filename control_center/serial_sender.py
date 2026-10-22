import serial
import serial.tools.list_ports
import time


class SerialSender:
    def __init__(self, baudrate=115200):
        """Initializes the serial configuration and sets up auto-detection."""
        self.baudrate = baudrate
        self.ser = None
        self.port = self.find_esp32_port()
        self._receive_buffer = bytearray()

    def find_esp32_port(self):
        """Find an unambiguous USB-serial target; never silently choose among devices."""
        ports = list(serial.tools.list_ports.comports())
        print("Scanning available COM ports...")

        matches = []
        for p in ports:
            print(f"Found: {p.device} - {p.description}")
            # Look for common ESP32 USB-to-UART bridge drivers (CP210x, CH340, or generic USB Serial)
            desc = p.description.lower()
            if "cp210" in desc or "ch340" in desc or "usb serial" in desc or "ch341" in desc:
                matches.append(p.device)

        if len(matches) == 1:
            print(f"🚀 Match found! Target hardware detected on: {matches[0]}")
            return matches[0]
        if len(matches) > 1:
            print("⚠️ Multiple USB-serial devices found; disconnect extras before connecting.")
            return None

        # A lone unrecognized port is a reasonable fallback; multiple ports are ambiguous.
        if len(ports) == 1:
            print(f"⚠️ Using the only available serial device: {ports[0].device}")
            return ports[0].device
        if len(ports) > 1:
            print("⚠️ Multiple unknown serial devices found; refusing to choose one automatically.")
            return None

        print("❌ No COM ports detected. Please plug in your ESP32.")
        return None

    def connect(self):
        """Opens the serial connection and sends a safe stop to wake the radar return path."""
        if self.ser and self.ser.is_open:
            self.ser.close()

        # Re-scan on reconnect in case the ESP32 was plugged into a different port.
        self.port = self.find_esp32_port()
        if not self.port:
            print("Connection aborted: No target port available.")
            return False

        try:
            self.ser = serial.Serial(self.port, self.baudrate, timeout=0)
            self._receive_buffer.clear()
            # Give the ESP32 time to reboot and initialize ESP-NOW after the serial line opens.
            time.sleep(2)
            if not self.send_command("S", 0):
                return False
            print(f"✅ Successfully linked to ESP32 on {self.port}")
            return True
        except serial.SerialException as e:
            print(f"❌ Failed to open port {self.port}: {e}")
            self.ser = None
            return False

    def send_command(self, command_str, speed=0):
        """Send COMMAND:SPEED for the transmitter's ESP-NOW GestureMessage."""
        if self.ser and self.ser.is_open:
            speed_value = max(0, min(255, int(speed)))
            packet = f"{command_str}:{speed_value}\n".encode("utf-8")
            try:
                self.ser.write(packet)
                return True
            except serial.SerialException as e:
                print(f"Serial command write failed: {e}")
                self.close()
                return False
        else:
            print("⚠️ Warning: Serial line dropped or not open. Transmission skipped.")
            return False

    def read_radar_telemetry(self):
        """Returns complete (angle_degrees, distance_cm) readings without blocking the UI."""
        if not self.ser or not self.ser.is_open:
            return []

        readings = []
        try:
            waiting = self.ser.in_waiting
            if waiting:
                self._receive_buffer.extend(self.ser.read(waiting))

            while b"\n" in self._receive_buffer:
                raw_line, _, remainder = self._receive_buffer.partition(b"\n")
                self._receive_buffer = bytearray(remainder)
                line = raw_line.decode("utf-8", errors="ignore").strip()
                if not line.startswith("RADAR:"):
                    continue

                parts = line.split(":")
                if len(parts) != 3:
                    continue
                try:
                    angle = int(parts[1])
                    distance_cm = int(parts[2])
                except ValueError:
                    continue
                if 0 <= angle <= 180 and 0 <= distance_cm <= 400:
                    readings.append((angle, distance_cm))
        except serial.SerialException as e:
            print(f"Radar telemetry read failed: {e}")
            self.close()

        return readings

    def close(self):
        """Safely drops the serial connection line."""
        if self.ser and self.ser.is_open:
            self.ser.close()
            print("Serial connection cleanly closed.")
