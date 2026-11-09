<div align="center">

# 🚀 Manus AD Lunam

### *"Hands to the Moon"*

[![MIT License](https://img.shields.io/badge/License-MIT-green.svg)](https://choosealicense.com/licenses/mit/)
[![GitHub Stars](https://img.shields.io/github/stars/Hanoon-Shameer/Manus-AD-Lunam.svg)](https://github.com/Hanoon-Shameer/Manus-AD-Lunam/stargazers)
[![GitHub Forks](https://img.shields.io/github/forks/Hanoon-Shameer/Manus-AD-Lunam.svg)](https://github.com/Hanoon-Shameer/Manus-AD-Lunam/network)
[![GitHub Issues](https://img.shields.io/github/issues/Hanoon-Shameer/Manus-AD-Lunam.svg)](https://github.com/Hanoon-Shameer/Manus-AD-Lunam/issues)
[![Website](https://img.shields.io/website?url=https%3A%2F%2Fmanus-ad-lunam.surge.sh)](https://manus-ad-lunam.surge.sh)

**Control a lunar rover with the power of your hands using advanced gesture recognition!**

[View Demo](https://manus-ad-lunam.surge.sh) · [Report Bug](https://github.com/Hanoon-Shameer/Manus-AD-Lunam/issues) · [Request Feature](https://github.com/Hanoon-Shameer/Manus-AD-Lunam/issues)

</div>

---

## 📖 About The Project

**Manus AD Lunam** (Latin: *Hands to the Moon*) is an innovative lunar rover control system that uses hand gesture recognition to navigate and operate a rover in real-time. This project combines computer vision, embedded systems, and mobile technology to create an intuitive and futuristic control interface.

<div align="center">

### 🎯 Project Components

| Component | Technology | Description |
|-----------|-----------|-------------|
| 🎮 **Control Center** | Python, OpenCV, CustomTkinter | Hand gesture recognition dashboard |
| 🤖 **Rover Firmware** | C/C++, Arduino/ESP32 | Embedded control system |
| 📱 **Mesh Mobile App** | Kotlin, Android | Mobile control interface |

</div>

---

## ✨ Features

- 🖐️ **Real-time Hand Gesture Recognition** - Control the rover using intuitive hand movements
- 📊 **Live Dashboard Interface** - Monitor rover status and camera feed in real-time
- 📡 **Wireless Communication** - Seamless mesh network connectivity
- 📱 **Mobile App Support** - Control from your Android device
- 🎥 **Video Streaming** - Live video feed from the rover's camera
- 🔧 **Modular Architecture** - Easy to extend and customize

---

## 🖼️ Gallery

<div align="center">

### Rover Views

<table>
  <tr>
    <td width="50%">
      <img src="assets/front view of raw rover.jpg" alt="Front View" />
      <p align="center"><b>Front View</b></p>
    </td>
    <td width="50%">
      <img src="assets/top view of iraw rover.jpg" alt="Top View" />
      <p align="center"><b>Top View</b></p>
    </td>
  </tr>
</table>

</div>

---

## 🚀 Getting Started

### Prerequisites

- Python 3.8+
- OpenCV
- Arduino IDE or PlatformIO
- Android Studio (for mobile app)
- Webcam for gesture recognition

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/Hanoon-Shameer/Manus-AD-Lunam.git
   cd Manus-AD-Lunam
   ```

2. **Set up the Control Center**
   ```bash
   cd control_center
   pip install -r requirements.txt  # If requirements file exists
   python main.py
   ```

3. **Flash the Rover Firmware**
   ```bash
   cd firmware
   # Open with Arduino IDE or PlatformIO and flash to your board
   ```

4. **Build the Mobile App**
   ```bash
   cd mesh_mobile_app
   ./gradlew build
   ```

---

## 🎮 Usage

1. **Launch the Control Center Dashboard**
   ```bash
   python control_center/main.py
   ```

2. **Connect to the Rover**
   - Ensure the rover is powered on and within range
   - Select the appropriate COM port in the dashboard

3. **Start Gesture Control**
   - Position your hand in front of the camera
   - Use predefined gestures to control the rover:
     - ✋ Open palm - Stop
     - 👊 Fist - Move forward
     - ☝️ Point left/right - Turn
     - And more!

4. **Monitor Performance**
   - View live camera feed
   - Check rover telemetry
   - Monitor connection status

---

## 🏗️ Project Structure

```
Manus-AD-Lunam/
├── 📂 control_center/          # Python-based control dashboard
│   ├── main.py                 # Main application entry point
│   ├── ui_dashboard.py         # Dashboard UI components
│   ├── gesture_controller.py   # Gesture recognition logic
│   ├── hand_detector.py        # Hand detection module
│   └── serial_sender.py        # Serial communication handler
├── 📂 firmware/                # Rover embedded firmware
│   ├── rover_receiver/         # Receiver module code
│   └── rover_transmitter/      # Transmitter module code
├── 📂 mesh_mobile_app/         # Android mobile application
│   └── app/                    # Mobile app source code
└── 📂 assets/                  # Project assets and images
```

---

## 🛠️ Technologies Used

<div align="center">

![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white)
![OpenCV](https://img.shields.io/badge/OpenCV-5C3EE8?style=for-the-badge&logo=opencv&logoColor=white)
![Arduino](https://img.shields.io/badge/Arduino-00979D?style=for-the-badge&logo=arduino&logoColor=white)
![Kotlin](https://img.shields.io/badge/Kotlin-7F52FF?style=for-the-badge&logo=kotlin&logoColor=white)
![Android](https://img.shields.io/badge/Android-3DDC84?style=for-the-badge&logo=android&logoColor=white)

</div>

---

## 🤝 Contributing

Contributions are what make the open source community such an amazing place to learn, inspire, and create. Any contributions you make are **greatly appreciated**.

1. Fork the Project
2. Create your Feature Branch (`git checkout -b feature/AmazingFeature`)
3. Commit your Changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the Branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

---

## 👥 Crew

<div align="center">

| Role | Member | GitHub |
|------|--------|--------|
| 🔧 **Hardware Specialist** | Hanoon Shameer | [@Hanoon-Shameer](https://github.com/Hanoon-Shameer) |
| 💻 **Programmer** | Abhay Vinod | [@sn0pox](https://github.com/sn0pox) |
| 🎨 **Designer** | Syed Sadiq | [@syed-sadiq-2009](https://github.com/syed-sadiq-2009) |

</div>

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

---

<div align="center">

## 🌐 Experience It Live

### **[🚀 Launch Demo →](https://manus-ad-lunam.surge.sh)**

<sub>See the project in action at **manus-ad-lunam.surge.sh**</sub>

---

### ⭐ Star this repository if you found it helpful!

**Made with ❤️ and a passion for robotics**

</div>
