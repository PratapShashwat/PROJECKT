# Smart Face Recognition Door Lock

This project is a comprehensive, UI-driven security system that uses facial recognition to control a solenoid door lock. It is built with Python, OpenCV, and PyQt5, and includes advanced features like anti-spoofing liveness detection, a full administrative panel, and hardware-based door sensors.

## 🚀 Key Features

* **Secure Facial Recognition:** Uses OpenCV's `LBPHFaceRecognizer` to grant access only to registered users.
* **Liveness Detection (Anti-Spoofing):** Integrated with Google's `MediaPipe` to perform a mandatory blink-detection test. This prevents spoofing attacks using static photos or videos.
* **Hardware "Door Ajar" Sensor:** Includes code for an Arduino-powered ultrasonic sensor (HC-SR04). If the door is physically left open for too long (configurable time), the UI will show an alert and play a sound.
* **Full Admin Panel:** A password-protected backend (`admin_panel.py`) allows for complete system management:
    * **Settings:** Configure all system timers, thresholds, and hardware settings.
    * **User Management:** Add new users, delete users, and add more samples to existing users.
    * **Access Log:** View a time-stamped CSV log of all unlock, lock, and alert events.
    * **Intruder Photos:** View a gallery of all saved photos from "Unknown" person alerts.
* **Intelligent Data Management:**
    * **Rolling Updates:** When adding samples to a user who is already at the limit, the system automatically deletes 10% of the oldest photos and adds new ones.
    * **Auto-Cleanup:** On admin login, the system automatically purges access logs older than 7 days and intruder photos older than 30 days.
* **Manual Overrides:**
    * **Password Unlock:** A "Manual Unlock" button on the main screen allows password-based entry if recognition fails.
    * **"Lock Now" Button:** A red button appears when the door is unlocked, allowing you to lock it immediately instead of waiting for the timer.
* **Clean & Manageable Code:**
    * All backend logic (camera, Arduino, recognition) is separated into `recognition_thread.py` to ensure a smooth, non-freezing UI.
    * All styling is externalized into `style.css`.

---

## ⚙️ Hardware Requirements

1.  **PC with Webcam:** To run the main Python application.
2.  **Arduino Uno** (or any compatible board).
3.  **5V Relay Module:** To safely control the 12V lock with the 5V Arduino.
4.  **12V Solenoid Door Lock.**
5.  **Ultrasonic Sensor (HC-SR04):** To detect if the door is open.
6.  **External 12V Power Supply:** For the solenoid lock.
7.  Breadboard and jumper wires.

### Hardware Connections

Upload the code from `project/code/arduino_code/arduino_code.ino` to your Arduino.

* **Relay Module:**
    * `VCC` -> Arduino `5V`
    * `GND` -> Arduino `GND`
    * `IN` -> Arduino `Pin 13`
* **Ultrasonic Sensor (HC-SR04):**
    * `VCC` -> Arduino `5V`
    * `GND` -> Arduino `GND`
    * `TRIG` -> Arduino `Pin 9`
    * `ECHO` -> Arduino `Pin 10`
* **Solenoid Lock:**
    * Connect the `+` wire of the 12V power supply to the `COM` (Common) pin on the relay.
    * Connect the `+` wire of the solenoid lock to the `NO` (Normally Open) pin on the relay.
    * Connect the `-` wire of the solenoid lock and the `-` wire of the 12V power supply together.

---

## 💻 Software Setup (Using a Virtual Environment)

### 1. Create a Virtual Environment
It is highly recommended to run this in a virtual environment (`.venv`) to avoid package conflicts.
```bash
# Navigate to your 'project' folder
cd path/to/your/project

# Create the virtual environment
python -m venv .venv

### 2. Activate the Environment

**On Windows:**
```bash
.\.venv\Scripts\activate
```

**On macOS/Linux:**
```bash
source .venv/bin/activate
```

(Your terminal prompt should now show `(.venv)`.)

---

### 3. Install Dependencies

Install all required Python libraries:

```bash
pip install opencv-python
pip install mediapipe
pip install PyQt5
pip install pyserial
pip install numpy
pip install pygame
pip install gTTS
pip install playsound==1.2.2
```

> **Windows Prerequisite:**  
> `mediapipe` requires the **Microsoft Visual C++ Redistributable**.  
> If you get a “DLL load failed” error, download and install the **x64** version from Microsoft’s website, then restart your computer.

---

### 4. First-Time Configuration

Run the application for the first time from within your code directory:

```bash
cd code
python main_ui.py
```

The program will run but may show an error in the terminal (e.g., `"Failed to open port..."`).  
This is **normal**.

Close the application. A new file named `config.json` has been created in your project folder.

Open `config.json` and change:
```
"ARDUINO_PORT": "COM5"
```
to your Arduino’s actual port (e.g., `"COM7"`, `"COM3"`, or `"/dev/ttyUSB0"` on Linux).

Re-run:
```bash
python main_ui.py
```
The system will now connect to your Arduino.

---

## 📖 How to Use

### 🔐 Daily Operation

1. Run:
   ```bash
   python main_ui.py
   ```
2. The UI will show **"LOCKED"**.  
3. Look at the camera. The info panel will show **"LIVENESS CHECK"** and ask you to blink.  
4. Blink 1–2 times. The info panel will show **"Liveness OK"**.  
5. The system will now try to recognize you.

**Success:**  
The status changes to **"UNLOCKED"**, your name appears, and the door unlocks. A red **"Lock Now"** button appears.

**Failure:**  
The status shows **"ALERT: UNKNOWN"**, a photo is saved, and an alert is logged.

If you do nothing, the door will automatically lock after the countdown.  
If you want to lock it sooner, press **"Lock Now"**.

---

### 🔑 Manual Unlock

If the camera fails to see you (e.g., poor lighting), click **"Manual Unlock"** and enter the admin password to unlock the door.

---

### ⚙️ Admin Panel

Click **"Admin Login"** and enter the admin password (**default:** `admin`).

The camera feed will stop, and the main UI will show **"ADMIN MODE"**.  
The Admin Panel will open.

---

#### 🧭 Settings Tab

Here you can control the core logic of the app.  
All changes are saved to `config.json` and applied when you close the admin panel.

| Setting | Description |
|----------|--------------|
| **Arduino Port** | The COM port for your Arduino. |
| **Intent Time** | How long a known user must look at the camera (in seconds) before it unlocks. |
| **Alert Time** | How long an unknown user can look before an **ALERT** is triggered. |
| **Door Ajar Timeout** | How long the door can stay open before the sensor sends an alert. |
| **Unlock Countdown** | How long the door remains unlocked. |
| **Confidence Threshold** | % required to be considered a match (e.g., `86%`). |
| **Liveness Blinks** | Number of blinks required to pass the anti-spoofing check. |
| **Max Samples / User** | Maximum photos stored per user. |
| **Admin Password** | Change the admin panel and manual unlock password. |

---

#### 👥 User Management Tab

- **Add New User:**  
  Type a username (no spaces, e.g., `john_doe`) and click **"Create New User"** to launch data collection.

- **Manage Existing Users:**  
  * **Refresh List:** Reloads the list of users from the `face_images` folder.  
  * **Add More Samples:** Select a user, then click to collect more data (uses rolling updates).  
  * **Delete Selected User:** Permanently removes the selected user's data.

---

#### 🧾 Access Log Tab

Displays a table of all events from `access_log.csv` (newest first).

---

#### 📸 Intruder Photos Tab

Shows a scrollable gallery of all photos saved from **"ALERT: UNKNOWN"** events.
