import cv2
import mediapipe
import sys
import numpy as np
import os
import pygame 
import threading
from PyQt5.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, 
                             QLabel, QPushButton, QMainWindow, QSizePolicy,
                             QMessageBox)
from PyQt5.QtGui import QFont, QPixmap, QImage
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, pyqtSlot

from recognition_thread import RecognitionThread, ArduinoRelay
from admin_login_dialog import LoginDialog 
from config_manager import ConfigManager
from admin_panel import AdminPanel
import audio_manager # <-- NEW

# -------------------------------------------------------------------
# --- Main Window (UI) ---
# -------------------------------------------------------------------
class MainWindow(QMainWindow):
    manual_unlock_signal = pyqtSignal()
    manual_lock_signal = pyqtSignal()
    
    def __init__(self):
        super().__init__()

        self.config_manager = ConfigManager()
        self.config = self.config_manager.get_all()
        
        self.door_alert_popup = None
        
        # --- *** UPDATED: Initialize Audio Manager *** ---
        try:
            # We no longer init pygame here, the manager does it.
            audio_manager.init_audio()
        except Exception as e:
            print(f"Could not initialize audio manager: {e}")
        # --- *** END UPDATE *** ---

        self.setWindowTitle("Face Recognition Security System")
        self.setGeometry(100, 100, 800, 600)
        self.setMinimumSize(640, 480)
        
        try:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            style_path = os.path.join(script_dir, "style.css")
            with open(style_path, "r") as f:
                self.setStyleSheet(f.read())
        except Exception as e:
            print(f"Could not load stylesheet: {e}")
            self.setStyleSheet("QWidget { background-color: #2E2E2E; color: #FFFFFF; }")

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

        self.manual_lock_button = QPushButton("Lock Now")
        self.manual_lock_button.setObjectName("LockNowButton")
        self.manual_lock_button.clicked.connect(self.manual_lock_signal.emit)
        self.manual_lock_button.hide() 

        self.manual_unlock_button = QPushButton("Manual Unlock")
        self.manual_unlock_button.setObjectName("UnlockButton")
        self.manual_unlock_button.clicked.connect(self.open_manual_unlock)

        self.admin_button = QPushButton("Admin Login")
        self.admin_button.clicked.connect(self.open_admin_panel)

        status_layout.addStretch(1)
        status_layout.addWidget(self.status_label)
        status_layout.addWidget(self.info_label)
        status_layout.addStretch(1)
        status_layout.addWidget(self.manual_lock_button)
        status_layout.addWidget(self.manual_unlock_button)
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
        
        if not self.worker.setup(self.config, self.config['ARDUINO_PORT'], self.config['ARDUINO_BAUD']):
            self.worker.info_updated.connect(lambda msg: self.show_error_popup(msg))
            self.worker.emit_error("Fatal setup error. Check logs.")
            return

        # Connect signals
        self.worker.frame_ready.connect(self.display_frame)
        self.worker.status_updated.connect(self.set_status)
        self.worker.info_updated.connect(self.set_info)
        self.manual_unlock_signal.connect(self.worker.on_manual_unlock)
        self.manual_lock_signal.connect(self.worker.on_manual_lock)
        self.worker.door_alert_signal.connect(self.show_door_alert)
        
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
        
        if text == "UNLOCKED":
            self.manual_lock_button.show()
        else:
            self.manual_lock_button.hide()

    @pyqtSlot(str)
    def set_info(self, text):
        self.info_label.setText(text)

    # --- *** FUNCTION REMOVED *** ---
    # def create_beep(...):
    # --- *** FUNCTION REMOVED *** ---
    # def play_alert_sound(...):
    # --- *** END REMOVAL *** ---
    
    # --- *** FUNCTION UPDATED *** ---
    @pyqtSlot(str, str)
    def show_door_alert(self, title, message):
        """Shows a non-spamming popup for the door alert."""
        if "Closed" not in title:
            self.set_status("DOOR AJAR", "#FFA500")
            audio_manager.speak("Door Ajar Alert") # <-- UPDATED
            
            if self.door_alert_popup is None or not self.door_alert_popup.isVisible():
                self.door_alert_popup = QMessageBox.warning(self, title, message)
                self.door_alert_popup.finished.connect(lambda: self.set_status("LOCKED", "#FF3333"))
        else:
            if self.door_alert_popup and self.door_alert_popup.isVisible():
                self.door_alert_popup.close()
            if not self.worker.in_countdown:
                self.set_status("LOCKED", "#FF3333")
    # --- *** END FUNCTION UPDATE *** ---

    def show_error_popup(self, message):
        QMessageBox.critical(self, "Fatal Error", message)

    def convert_cv_to_qt(self, cv_img):
        rgb_image = cv2.cvtColor(cv_img, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb_image.shape
        bytes_per_line = ch * w
        convert_to_Qt_format = QImage(rgb_image.data, w, h, bytes_per_line, QImage.Format_RGB888)
        return convert_to_Qt_format.copy()

    def open_manual_unlock(self):
        if not (hasattr(self, 'worker') and self.worker.isRunning()):
            self.set_info("System is not ready. Cannot manually unlock.")
            return
            
        dialog = LoginDialog(mode='unlock', parent=self)
        
        if dialog.exec_(): 
            if dialog.was_login_successful():
                self.manual_unlock_signal.emit()

    def open_admin_panel(self):
        dialog = LoginDialog(mode='admin', parent=self)
        if not dialog.exec_():
            return
        
        if not dialog.was_login_successful():
            # Already handled by dialog
            return
            
        if hasattr(self, 'worker'):
            try:
                self.worker.relay.send("L")
                audio_manager.speak("Admin override. Door locked.") # <-- UPDATED
            except Exception as e:
                print(f"Could not send admin lock command: {e}")
            
            try:
                self.worker.frame_ready.disconnect()
                self.worker.status_updated.disconnect()
                self.worker.info_updated.disconnect()
                self.manual_unlock_signal.disconnect()
                self.manual_lock_signal.disconnect()
                self.worker.door_alert_signal.disconnect()
            except TypeError:
                pass 
            
            self.worker.stop()
            self.worker.wait()

        self.video_label.setText("ADMIN MODE\n\nCamera paused.")
        self.set_status("ADMIN", "#007ACC")
        self.set_info("Admin panel is open. Camera is paused.")
        self.manual_lock_button.hide() 
        
        QApplication.processEvents()
        
        QTimer.singleShot(50, self.launch_admin_panel_dialog)

    def launch_admin_panel_dialog(self):
        audio_manager.speak("Admin Panel opened.") # <-- NEW
        self.admin_panel = AdminPanel(self.config_manager)
        self.admin_panel.exec_() 

        print("Admin Panel closed. Reloading config and restarting camera...")
        audio_manager.speak("Admin Panel closed. Restarting camera.") # <-- NEW
        self.config = self.config_manager.load_config()
        self.start_recognition()

    def closeEvent(self, event):
        print("Closing application...")
        audio_manager.speak("System shutting down.") # <-- NEW
        if hasattr(self, 'worker'):
            self.worker.stop()
            self.worker.wait()
        audio_manager.quit_audio() # <-- UPDATED
        event.accept()

# --- Main execution ---
if __name__ == '__main__':
    import cv2
    import mediapipe
    
    app = QApplication(sys.argv)
    
    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        style_path = os.path.join(script_dir, "style.css")
        with open(style_path, "r") as f:
            app.setStyleSheet(f.read())
    except Exception as e:
        print(f"Could not load stylesheet: {e}")

    window = MainWindow()
    window.show()
    sys.exit(app.exec_())

