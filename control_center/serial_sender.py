import serial
import serial.tools.list_ports
import time

class SerialSender:
    def __init__(self, baudrate=115200):
        """Initializes the serial configuration and sets up auto-detection."""
        self.baudrate = baudrate
        self.ser = None
        self.port = self.find_esp32_port()

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
        """Opens the connection using the auto-detected port."""
        if not self.port:
            print("Connection aborted: No target port available.")
            return False
            
        try:
            self.ser = serial.Serial(self.port, self.baudrate, timeout=1)
            # Give the ESP32 2 seconds to auto-reboot and sync up after the serial line opens
            time.sleep(2) 
            print(f"✅ Successfully linked to ESP32 on {self.port}")
            return True
        except serial.SerialException as e:
            print(f"❌ Failed to open port {self.port}: {e}")
            return False

    def send_command(self, command_str):
        """Encodes and pushes the lightweight steering/pedal code down the wire."""
        if self.ser and self.ser.is_open:
            packet = f"{command_str}\n".encode('utf-8')
            self.ser.write(packet)
        else:
            print("⚠️ Warning: Serial line dropped or not open. Transmission skipped.")

    def close(self):
        """Safely drops the serial connection line."""
        if self.ser and self.ser.is_open:
            self.ser.close()
            print("Serial connection cleanly closed.")