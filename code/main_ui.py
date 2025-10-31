import sys
import cv2
import numpy as np
import os
import time
import serial
import csv
from datetime import datetime
from PyQt5.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, 
                             QLabel, QPushButton, QMainWindow, QSizePolicy,
                             QMessageBox)
from PyQt5.QtGui import QFont, QPixmap, QImage
from PyQt5.QtCore import Qt, QTimer, QThread, pyqtSignal, pyqtSlot # <-- Add pyqtSlot

# --- IMPORT THE RENAMED DIALOG ---
from admin_login_dialog import LoginDialog 
from config_manager import ConfigManager
from admin_panel import AdminPanel

# -------------------------------------------------------------------
# --- Worker Thread for Face Recognition ---
# -------------------------------------------------------------------
class RecognitionThread(QThread):
    frame_ready = pyqtSignal(np.ndarray)
    status_updated = pyqtSignal(str, str)
    info_updated = pyqtSignal(str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.running = True
        self.config = {}
        script_dir = os.path.dirname(os.path.abspath(__file__))
        self.log_file = os.path.join(script_dir, "..", "access_log.csv")
        self.intruder_folder = os.path.join(script_dir, "..", "intruders")
        self.haarcascade_path = os.path.normpath(os.path.join(script_dir, "..", "requirements", "haarcascade_frontalface_default.xml"))
        self.data_path = os.path.join(script_dir, "..", "face_images")
        self.face_classifier = None
        self.model = None
        self.user_map = {}
        self.relay = None
        self.cap = None
        
        # --- State variables to be controlled by signals ---
        self.in_countdown = False
        self.unlock_time = None
        self.recognized_user = None

    def setup(self, config, arduino_port):
        self.config = config
        self.relay = ArduinoRelay(arduino_port)
        if not self.relay.ser:
            self.emit_error(f"Failed to open port {arduino_port}. Running in VIRTUAL mode.")

        if not os.path.exists(self.haarcascade_path):
            self.emit_error("Haarcascade file not found. Please check 'requirements' folder.")
            return False
        self.face_classifier = cv2.CascadeClassifier(self.haarcascade_path)

        if not self.train_model():
            return False
            
        return True

    def train_model(self):
        self.info_updated.emit("Loading training data...")
        if not os.path.exists(self.data_path):
            self.emit_error("Fatal: 'face_images' folder not found. Please run data collection.")
            return False

        dirs = [d for d in os.listdir(self.data_path) if os.path.isdir(os.path.join(self.data_path,d))]
        Training_data, Labels = [], []
        self.user_map = {}
        
        for idx, user in enumerate(dirs):
            user_folder = os.path.join(self.data_path, user)
            self.user_map[idx] = user
            for file in os.listdir(user_folder):
                if file.lower().endswith('.jpg'):
                    img_path = os.path.join(user_folder, file)
                    img = cv2.imread(img_path, cv2.IMREAD_GRAYSCALE)
                    if img is not None:
                        Training_data.append(img)
                        Labels.append(idx)

        if len(Training_data) == 0:
            self.emit_error("No training data found in 'face_images'. Please add users.")
            return False

        Labels = np.asarray(Labels, dtype=np.int32)
        self.model = cv2.face.LBPHFaceRecognizer_create()
        self.model.train(np.asarray(Training_data), Labels)
        print(f"Training complete. Known users: {self.user_map.values()}")
        self.info_updated.emit("Training complete. System ready.")
        return True

    def find_largest_face(self, img_gray):
        faces = self.face_classifier.detectMultiScale(img_gray, 1.3, 5)
        if len(faces) == 0:
            return None, None
        (x, y, w, h) = max(faces, key=lambda f: f[2] * f[3])
        roi = cv2.resize(img_gray[y:y + h, x:x + w], (200, 200))
        return roi, (x, y, w, h)

    def log_event(self, event_type, username, image=None):
        timestamp = datetime.now()
        try:
            file_exists = os.path.isfile(self.log_file)
            with open(self.log_file, 'a', newline='') as f:
                writer = csv.writer(f)
                if not file_exists:
                    writer.writerow(["Timestamp", "Event_Type", "User"]) 
                writer.writerow([timestamp.strftime("%Y-%m-%d %H:%M:%S"), event_type, username])
        except Exception as e:
            print(f"!!! Log file error: {e}")

        if image is not None and event_type == "ALERT_UNKNOWN":
            filename = f"ALERT_{username}_{timestamp.strftime('%Y%m%d_%H%M%S')}.jpg"
            filepath = os.path.join(self.intruder_folder, filename)
            try:
                cv2.imwrite(filepath, image)
                print(f"Saved alert snapshot: {filepath}")
            except Exception as e:
                print(f"!!! FAILED to save snapshot to {filepath}: {e}")

    def run(self):
        self.cap = cv2.VideoCapture(0)
        if not self.cap.isOpened():
            self.emit_error("Camera not detected.")
            self.running = False
            return

        print("Recognition thread started.")
        self.speak("System activated.")

        intent_start_time = None
        alert_start_time = None 
        alert_triggered = False 

        while self.running:
            ret, frame = self.cap.read()
            if not ret:
                print("Camera feed lost.")
                time.sleep(1.0)
                continue
            
            frame = cv2.flip(frame, 1) # Mirror
            frame_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            frame_display = frame.copy()

            # --- State 1: Door is Unlocked (Countdown) ---
            # self.in_countdown is now controlled by this thread AND external signals
            if self.in_countdown:
                elapsed = time.time() - self.unlock_time
                remaining = max(0, self.config['COUNTDOWN_SECONDS'] - int(elapsed))
                
                self.status_updated.emit("UNLOCKED", "#00FF00")
                self.info_updated.emit(f"Welcome {self.recognized_user}\n\nLocking in {remaining}s")
                
                if remaining == 0:
                    self.speak("Door locked.")
                    self.relay.send("L")
                    self.log_event("LOCK_AUTO", "System")
                    self.in_countdown = False; self.unlock_time = None; self.recognized_user = None
                    intent_start_time = None; alert_start_time = None; alert_triggered = False

            # --- State 2: Door is Locked (Recognition) ---
            else:
                face_roi, face_bounds = self.find_largest_face(frame_gray)
                
                if face_roi is None:
                    intent_start_time = None
                    alert_start_time = None
                    alert_triggered = False 
                    self.status_updated.emit("LOCKED", "#FF3333")
                    self.info_updated.emit("Please look at the camera.")
                
                else:
                    (x, y, w, h) = face_bounds
                    cv2.rectangle(frame_display, (x, y), (x + w, y + h), (0, 200, 255), 2)
                    
                    try:
                        result = self.model.predict(face_roi)
                        confidence = int((1 - result[1] / 300) * 100)
                        user_name = self.user_map.get(result[0], "Unknown")

                        if confidence >= self.config['CONFIDENCE_THRESH']:
                            alert_start_time = None
                            alert_triggered = False 
                            
                            if intent_start_time is None:
                                intent_start_time = time.time()
                            
                            intent_elapsed = time.time() - intent_start_time
                            
                            if intent_elapsed >= self.config['INTENT_TIME_SEC']:
                                # --- UNLOCK SUCCESS (FACE) ---
                                self.speak(f"Welcome {user_name}. Door unlocked.")
                                self.relay.send("U")
                                self.log_event("UNLOCK_FACE", user_name)
                                # --- SET STATE ---
                                self.in_countdown = True
                                self.unlock_time = time.time()
                                self.recognized_user = user_name
                            else:
                                self.status_updated.emit(f"Welcome {user_name}", "#00FF00")
                                self.info_updated.emit(f"Verifying intent...\n\nConfidence: {confidence}%")

                        else:
                            intent_start_time = None
                            
                            if alert_start_time is None:
                                alert_start_time = time.time()
                            
                            if (time.time() - alert_start_time > self.config['LOITER_TIME_SEC']) and not alert_triggered:
                                self.speak("Alert. Unknown person detected.") 
                                self.log_event("ALERT_UNKNOWN", "Unknown", image=frame)
                                alert_triggered = True
                            
                            self.status_updated.emit("ALERT: UNKNOWN", "#FF3333")
                            self.info_updated.emit(f"Confidence: {confidence}%")

                    except Exception as e:
                        print(f"Recognition error: {e}")
                        self.status_updated.emit("ERROR", "#FF3333")
                        self.info_updated.emit("Recognition error.")

            self.frame_ready.emit(frame_display)
            time.sleep(0.03)
        
        print("Shutting down recognition thread...")
        if self.cap:
            self.cap.release()
        if self.relay:
            self.relay.close()

    def speak(self, text):
        print(f"SPEAKING: {text}")

    def emit_error(self, message):
        print(f"ERROR: {message}")
        self.status_updated.emit("ERROR", "#FF3333")
        self.info_updated.emit(message)

    # --- NEW FUNCTION TO BE CALLED BY SIGNAL ---
    @pyqtSlot()
    def on_manual_unlock(self):
        """Triggers the unlock countdown manually."""
        if self.in_countdown:
            print("Manual unlock requested, but already in countdown.")
            return # Already unlocked
            
        print("Manual override: Unlocking door.")
        self.speak("Manual override. Door unlocked.")
        self.relay.send("U")
        self.log_event("UNLOCK_MANUAL", "Admin")
        
        # --- SET STATE ---
        self.in_countdown = True
        self.unlock_time = time.time()
        self.recognized_user = "Admin Override"

    def stop(self):
        self.running = False

# -------------------------------------------------------------------
# --- Arduino Relay Class (Unchanged) ---
# -------------------------------------------------------------------
class ArduinoRelay:
    def __init__(self, port, baud=115200, timeout=1):
        self.port = port
        self.baud = baud
        try:
            self.ser = serial.Serial(port, baud, timeout=timeout)
            time.sleep(2)  
            print(f"Serial port {port} opened successfully.")
        except Exception as e:
            print(f"FAILED to open serial port {port}: {e}")
            print("Running in 'NO_RELAY' mode. Door will not unlock.")
            self.ser = None

    def send(self, msg):
        if not self.ser:
            print(f"VIRTUAL RELAY: {msg}") 
            return True
        try:
            self.ser.write((msg + '\n').encode('utf-8'))
            self.ser.flush()
            ack = self.ser.readline().decode('utf-8', errors='ignore').strip()
            print(f"Arduino ACK: {ack}")
            return True
        except Exception as e:
            print(f"Serial write error: {e}")
            return False

    def close(self):
        if self.ser:
            self.send("L") 
            self.ser.close()
            print("Serial port closed.")

# -------------------------------------------------------------------
# --- Main Window (UI) ---
# -------------------------------------------------------------------
class MainWindow(QMainWindow):
    # --- NEW SIGNAL: To trigger the worker thread ---
    manual_unlock_signal = pyqtSignal()
    
    def __init__(self):
        super().__init__()

        self.config_manager = ConfigManager()
        self.config = self.config_manager.get_all()

        self.setWindowTitle("Face Recognition Security System")
        self.setGeometry(100, 100, 800, 600)
        self.setMinimumSize(640, 480)
        
        self.setStyleSheet("""
            QWidget {
                background-color: #2E2E2E;
                color: #FFFFFF;
                font-family: Arial;
            }
            QLabel#VideoLabel {
                background-color: #000000;
                border: 2px solid #555555;
            }
            QLabel#StatusLabel {
                font-size: 32px;
                font-weight: bold;
            }
            QLabel#InfoLabel {
                font-size: 16px;
                color: #AAAAAA;
            }
            QPushButton {
                background-color: #007ACC;
                border: none;
                padding: 10px;
                border-radius: 5px;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #005FA6;
            }
            /* --- NEW: Style for the manual unlock button --- */
            QPushButton#UnlockButton {
                background-color: #008f00; /* Green */
            }
            QPushButton#UnlockButton:hover {
                background-color: #006a00;
            }
        """)

        self.initUI()
        self.start_recognition()

    def initUI(self):
        self.video_label = QLabel(self)
        self.video_label.setObjectName("VideoLabel")
        self.video_label.setAlignment(Qt.AlignCenter)
        self.video_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        self.video_label.setText("INITIALIZING...")
        font = self.video_label.font()
        font.setPointSize(20)
        self.video_label.setFont(font)
        
        status_panel = QWidget()
        status_layout = QVBoxLayout()
        status_panel.setLayout(status_layout)
        status_panel.setFixedWidth(250)

        self.status_label = QLabel("LOCKED")
        self.status_label.setObjectName("StatusLabel")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("color: #FF3333;")
        self.status_label.setWordWrap(True)

        self.info_label = QLabel("Please look at the camera.")
        self.info_label.setObjectName("InfoLabel")
        self.info_label.setAlignment(Qt.AlignCenter)
        self.info_label.setWordWrap(True)
        self.info_label.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)

        # --- NEW: Manual Unlock Button ---
        self.manual_unlock_button = QPushButton("Manual Unlock")
        self.manual_unlock_button.setObjectName("UnlockButton")
        self.manual_unlock_button.clicked.connect(self.open_manual_unlock)

        self.admin_button = QPushButton("Admin Login")
        self.admin_button.clicked.connect(self.open_admin_panel)

        status_layout.addStretch(1)
        status_layout.addWidget(self.status_label)
        status_layout.addWidget(self.info_label)
        status_layout.addStretch(1)
        status_layout.addWidget(self.manual_unlock_button) # Add new button
        status_layout.addWidget(self.admin_button)
        status_layout.setContentsMargins(10, 10, 10, 10)

        main_layout = QHBoxLayout()
        main_layout.addWidget(self.video_label, 1) 
        main_layout.addWidget(status_panel)      

        central_widget = QWidget()
        central_widget.setLayout(main_layout)
        self.setCentralWidget(central_widget)

    def start_recognition(self):
        self.worker = RecognitionThread()
        
        if not self.worker.setup(self.config, self.config['ARDUINO_PORT']):
            self.worker.info_updated.connect(lambda msg: self.show_error_popup(msg))
            self.worker.emit_error("Fatal setup error. Check logs.")
            return

        # --- Connect signals ---
        self.worker.frame_ready.connect(self.display_frame)
        self.worker.status_updated.connect(self.set_status)
        self.worker.info_updated.connect(self.set_info)
        
        # --- NEW: Connect the manual unlock signal TO the worker's slot ---
        self.manual_unlock_signal.connect(self.worker.on_manual_unlock)
        
        self.worker.start()

    @pyqtSlot(np.ndarray)
    def display_frame(self, frame):
        qt_image = self.convert_cv_to_qt(frame)
        self.video_label.setPixmap(QPixmap.fromImage(qt_image).scaled(
            self.video_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
        ))

    @pyqtSlot(str, str)
    def set_status(self, text, color):
        self.status_label.setText(text)
        self.status_label.setStyleSheet(f"font-size: 32px; font-weight: bold; color: {color};")

    @pyqtSlot(str)
    def set_info(self, text):
        self.info_label.setText(text)

    def show_error_popup(self, message):
        QMessageBox.critical(self, "Fatal Error", message)

    def convert_cv_to_qt(self, cv_img):
        rgb_image = cv2.cvtColor(cv_img, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb_image.shape
        bytes_per_line = ch * w
        convert_to_Qt_format = QImage(rgb_image.data, w, h, bytes_per_line, QImage.Format_RGB888)
        return convert_to_Qt_format.copy()

    # --- NEW FUNCTION ---
    def open_manual_unlock(self):
        """Opens the password dialog for a manual unlock."""
        # Don't open if worker is dead
        if not (hasattr(self, 'worker') and self.worker.isRunning()):
            self.set_info("System is not ready. Cannot manually unlock.")
            return
            
        dialog = LoginDialog(mode='unlock', parent=self)
        
        if dialog.exec_(): # Returns True if 'accept()' was called
            if dialog.was_login_successful():
                # --- EMIT THE SIGNAL ---
                # This tells the worker thread to run its unlock function
                self.manual_unlock_signal.emit()

    def open_admin_panel(self):
        print("Login OK. Opening Admin Panel...")
        
        # Use the 'admin' mode dialog
        dialog = LoginDialog(mode='admin', parent=self)
        if not dialog.exec_():
            return # User cancelled
        
        if not dialog.was_login_successful():
            return # Password fail
            
        if hasattr(self, 'worker'):
            try:
                self.worker.relay.send("L")
                self.worker.speak("Admin override. Door locked.")
            except Exception as e:
                print(f"Could not send admin lock command: {e}")
            
            try:
                self.worker.frame_ready.disconnect()
                self.worker.status_updated.disconnect()
                self.worker.info_updated.disconnect()
            except TypeError:
                pass
            
            self.worker.stop()
            self.worker.wait()

        self.video_label.setText("ADMIN MODE\n\nCamera paused.")
        self.set_status("ADMIN", "#007ACC")
        self.set_info("Admin panel is open. Camera is paused.")
        
        QApplication.processEvents()
        
        QTimer.singleShot(50, self.launch_admin_panel_dialog)

    def launch_admin_panel_dialog(self):
        self.admin_panel = AdminPanel(self.config_manager)
        self.admin_panel.exec_() 

        print("Admin Panel closed. Reloading config and restarting camera...")
        self.config = self.config_manager.load_config()
        self.start_recognition() # Restart the thread

    def closeEvent(self, event):
        print("Closing application...")
        if hasattr(self, 'worker'):
            self.worker.stop()
            self.worker.wait()
        event.accept()

# --- Main execution ---
if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())