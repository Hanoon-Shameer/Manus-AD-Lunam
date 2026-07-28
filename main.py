import sys
import os
import ctypes

if sys.platform == "win32":
    myappid = "ManusADLunam.0.1"  # Arbitrary string unique to your application
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QIcon
from ui_dashboard import MADDashboard

def main():
    # Initialize the PyQt Application
    app = QApplication(sys.argv)

    # Set the application-level icon early so Windows taskbar and titlebar use it.
    icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.png")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    # Create and display the main control dashboard
    dashboard = MADDashboard()
    dashboard.show()

    # Run the application event loop and exit cleanly when closed
    sys.exit(app.exec())

if __name__ == "__main__":
    main()