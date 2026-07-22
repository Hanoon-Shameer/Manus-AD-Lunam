import sys
import ctypes

if sys.platform == "win32":
    myappid = "ManusADLunam.0.1"  # Arbitrary string unique to your application
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)

from PyQt6.QtWidgets import QApplication
from ui_dashboard import MADDashboard

def main():
    # Initialize the PyQt Application
    app = QApplication(sys.argv)
    
    # Create and display the main control dashboard
    dashboard = MADDashboard()
    dashboard.show()
    
    # Run the application event loop and exit cleanly when closed
    sys.exit(app.exec())

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MADDashboard()
    window.show()
    sys.exit(app.exec())