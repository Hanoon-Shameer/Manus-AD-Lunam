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
        """Scans system ports to automatically discover the ESP32."""
        ports = list(serial.tools.list_ports.comports())
        print("Scanning available COM ports...")

        for p in ports:
            print(f"Found: {p.device} - {p.description}")
            # Look for common ESP32 USB-to-UART bridge drivers (CP210x, CH340, or generic USB Serial)
            desc = p.description.lower()
            if "cp210" in desc or "ch340" in desc or "usb serial" in desc or "ch341" in desc:
                print(f"🚀 Match found! Target hardware detected on: {p.device}")
                return p.device

        # Fallback to the first available port if no exact driver name matches
        if ports:
            print(f"⚠️ No exact driver match, defaulting to first available: {ports[0].device}")
            return ports[0].device

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
            self.send_command("S")
            print(f"✅ Successfully linked to ESP32 on {self.port}")
            return True
        except serial.SerialException as e:
            print(f"❌ Failed to open port {self.port}: {e}")
            self.ser = None
            return False

    def send_command(self, command_str):
        """Encodes and pushes the lightweight steering/pedal code down the wire."""
        if self.ser and self.ser.is_open:
            packet = f"{command_str}\n".encode("utf-8")
            self.ser.write(packet)
        else:
            print("⚠️ Warning: Serial line dropped or not open. Transmission skipped.")

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

        return readings

    def close(self):
        """Safely drops the serial connection line."""
        if self.ser and self.ser.is_open:
            self.ser.close()
            print("Serial connection cleanly closed.")
