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

# --- Custom Application Modules ---
from recognition_thread import RecognitionThread, ArduinoRelay
from admin_login_dialog import LoginDialog 
from config_manager import ConfigManager
from admin_panel import AdminPanel
import audio_manager # Handles all text-to-speech feedback

# -------------------------------------------------------------------
# --- Main Window (UI) ---
# -------------------------------------------------------------------
class MainWindow(QMainWindow):
    """
    The main application window. It handles the UI, starts the 
    recognition thread, and displays the video feed and status.
    """
    
    # Signals to communicate from the UI (main thread) to the worker thread
    manual_unlock_signal = pyqtSignal()
    manual_lock_signal = pyqtSignal()
    
    def __init__(self):
        super().__init__()

        # Load application settings
        self.config_manager = ConfigManager()
        self.config = self.config_manager.get_all()
        
        # Used to prevent spamming the "Door Ajar" popup
        self.door_alert_popup = None
        
        # --- Initialize Audio Manager ---
        # This is called *once* at startup.
        try:
            audio_manager.init_audio()
        except Exception as e:
            print(f"Could not initialize audio manager: {e}")

        # --- Window Setup ---
        self.setWindowTitle("Face Recognition Security System")
        self.setGeometry(100, 100, 800, 600)
        self.setMinimumSize(640, 480)
        
        # Load external stylesheet
        try:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            style_path = os.path.join(script_dir, "style.css")
            with open(style_path, "r") as f:
                self.setStyleSheet(f.read())
        except Exception as e:
            print(f"Could not load stylesheet: {e}")
            # Fallback style if stylesheet fails
            self.setStyleSheet("QWidget { background-color: #2E2E2E; color: #FFFFFF; }")

        # Build the UI elements and start the camera
        self.initUI()
        self.start_recognition()

    def initUI(self):
        """Creates and arranges all UI widgets."""
        
        # --- Video Feed Label ---
        # This label will display the camera feed
        self.video_label = QLabel(self)
        self.video_label.setObjectName("VideoLabel")
        self.video_label.setAlignment(Qt.AlignCenter)
        self.video_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        self.video_label.setText("INITIALIZING...")
        font = self.video_label.font()
        font.setPointSize(20)
        self.video_label.setFont(font)
        
        # --- Status Panel (Right Sidebar) ---
        status_panel = QWidget()
        status_layout = QVBoxLayout()
        status_panel.setLayout(status_layout)
        status_panel.setFixedWidth(250)

        # Status Label (LOCKED, UNLOCKED, etc.)
        self.status_label = QLabel("LOCKED")
        self.status_label.setObjectName("StatusLabel")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("color: #FF3333;") # Default to red
        self.status_label.setWordWrap(True)

        # Info Label (Welcome, Look at camera, etc.)
        self.info_label = QLabel("Please look at the camera.")
        self.info_label.setObjectName("InfoLabel")
        self.info_label.setAlignment(Qt.AlignCenter)
        self.info_label.setWordWrap(True)
        self.info_label.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)

        # --- Buttons ---
        self.manual_lock_button = QPushButton("Lock Now")
        self.manual_lock_button.setObjectName("LockNowButton")
        self.manual_lock_button.clicked.connect(self.manual_lock_signal.emit)
        self.manual_lock_button.hide() # Only shown when unlocked

        self.manual_unlock_button = QPushButton("Manual Unlock")
        self.manual_unlock_button.setObjectName("UnlockButton")
        self.manual_unlock_button.clicked.connect(self.open_manual_unlock)

        self.admin_button = QPushButton("Admin Login")
        self.admin_button.clicked.connect(self.open_admin_panel)

        # --- Assemble Status Panel ---
        status_layout.addStretch(1)
        status_layout.addWidget(self.status_label)
        status_layout.addWidget(self.info_label)
        status_layout.addStretch(1)
        status_layout.addWidget(self.manual_lock_button)
        status_layout.addWidget(self.manual_unlock_button)
        status_layout.addWidget(self.admin_button)
        status_layout.setContentsMargins(10, 10, 10, 10)

        # --- Assemble Main Layout ---
        main_layout = QHBoxLayout()
        main_layout.addWidget(self.video_label, 1) # Video takes expanding space (1)
        main_layout.addWidget(status_panel)      
 
        central_widget = QWidget()
        central_widget.setLayout(main_layout)
        self.setCentralWidget(central_widget)

    def start_recognition(self):
        """Initializes and starts the background recognition thread."""
        self.worker = RecognitionThread()
        
        # Try to set up the worker. If it fails (e.g., no camera), show an error.
        if not self.worker.setup(self.config, self.config['ARDUINO_PORT'], self.config['ARDUINO_BAUD']):
            # Connect the info signal to the error popup
            self.worker.info_updated.connect(lambda msg: self.show_error_popup(msg))
            self.worker.emit_error("Fatal setup error. Check logs.")
            return

        # --- Connect signals from worker thread to UI slots ---
        self.worker.frame_ready.connect(self.display_frame)
        self.worker.status_updated.connect(self.set_status)
        self.worker.info_updated.connect(self.set_info)
        self.worker.door_alert_signal.connect(self.show_door_alert)
        
        # --- Connect signals from UI to worker thread ---
        self.manual_unlock_signal.connect(self.worker.on_manual_unlock)
        self.manual_lock_signal.connect(self.worker.on_manual_lock)
        
        # Start the thread's .run() method
        self.worker.start()

    # --- UI Update Slots (Called by Worker Thread) ---

    @pyqtSlot(np.ndarray)
    def display_frame(self, frame):
        """Updates the video_label with a new frame from the worker."""
        qt_image = self.convert_cv_to_qt(frame)
        self.video_label.setPixmap(QPixmap.fromImage(qt_image).scaled(
            self.video_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
        ))

    @pyqtSlot(str, str)
    def set_status(self, text, color):
        """Updates the main status label (LOCKED/UNLOCKED) and color."""
        self.status_label.setText(text)
        self.status_label.setStyleSheet(f"font-size: 32px; font-weight: bold; color: {color};")
        
        # Show the "Lock Now" button only when the door is unlocked
        if text == "UNLOCKED":
            self.manual_lock_button.show()
        else:
            self.manual_lock_button.hide()

    @pyqtSlot(str)
    def set_info(self, text):
        """Updates the informational text label."""
        self.info_label.setText(text)

    @pyqtSlot(str, str)
    def show_door_alert(self, title, message):
        """Handles the "Door Ajar" alert from the worker thread."""
        
        if "Closed" not in title:
            # --- Door is OPEN ---
            self.set_status("DOOR AJAR", "#FFA500") # Orange color
            audio_manager.speak("Door Ajar Alert") 

            # Spam prevention: Only create a new popup if one isn't active
            if self.door_alert_popup is None or not self.door_alert_popup.isVisible():
                msg = QMessageBox(self)
                msg.setIcon(QMessageBox.Warning)
                msg.setWindowTitle(title)
                msg.setText(message)
                msg.setStandardButtons(QMessageBox.Ok)

                self.door_alert_popup = msg # Store the instance

                # When the popup is closed, reset the status to LOCKED
                self.door_alert_popup.finished.connect(lambda: self.set_status("LOCKED", "#FF3333"))
                
                self.door_alert_popup.show() # Show non-blockingly
        else:
            # --- Door is CLOSED ---
            # If the popup is open, close it
            if self.door_alert_popup and self.door_alert_popup.isVisible():
                self.door_alert_popup.close()
            # Reset status only if not in an unlock countdown
            if not self.worker.in_countdown:
                self.set_status("LOCKED", "#FF3333")

    def show_error_popup(self, message):
        """Displays a fatal error message."""
        QMessageBox.critical(self, "Fatal Error", message)

    # --- Utility and Button Functions ---

    def convert_cv_to_qt(self, cv_img):
        """Converts an OpenCV BGR image to a Qt QImage (RGB)."""
        rgb_image = cv2.cvtColor(cv_img, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb_image.shape
        bytes_per_line = ch * w
        convert_to_Qt_format = QImage(rgb_image.data, w, h, bytes_per_line, QImage.Format_RGB888)
        return convert_to_Qt_format.copy()

    def open_manual_unlock(self):
        """Opens the password dialog for a manual override."""
        if not (hasattr(self, 'worker') and self.worker.isRunning()):
            self.set_info("System is not ready. Cannot manually unlock.")
            return
            
        dialog = LoginDialog(mode='unlock', parent=self)
        
        # .exec_() blocks until the dialog is closed
        if dialog.exec_(): 
            if dialog.was_login_successful():
                # Emit the signal to tell the worker thread to unlock
                self.manual_unlock_signal.emit()

    def open_admin_panel(self):
        """
        Handles the full admin login process:
        1. Authenticate
        2. Stop the recognition thread
        3. Open the AdminPanel
        """
        dialog = LoginDialog(mode='admin', parent=self)
        if not dialog.exec_():
            return # User cancelled
        
        if not dialog.was_login_successful():
            return # Password failed (handled by dialog)
            
        # --- Login Successful: Stop the Worker Thread ---
        if hasattr(self, 'worker'):
            try:
                # Send a final "Lock" command as a safety override
                self.worker.relay.send("L")
                audio_manager.speak("Admin override. Door locked.")
            except Exception as e:
                print(f"Could not send admin lock command: {e}")
            
            # Disconnect all signals to prevent crashes during shutdown
            try:
                self.worker.frame_ready.disconnect()
                self.worker.status_updated.disconnect()
                self.worker.info_updated.disconnect()
                self.manual_unlock_signal.disconnect()
                self.manual_lock_signal.disconnect()
                self.worker.door_alert_signal.disconnect()
            except TypeError:
                pass # Signals were already disconnected
            
            self.worker.stop()
            self.worker.wait() # Wait for thread to fully exit

        # --- Update UI to "Admin Mode" ---
        self.video_label.setText("ADMIN MODE\n\nCamera paused.")
        self.set_status("ADMIN", "#007ACC") # Blue color
        self.set_info("Admin panel is open. Camera is paused.")
        self.manual_lock_button.hide() 
        
        QApplication.processEvents() # Force UI to update
        
        # Use a QTimer to launch the modal dialog.
        # This allows the UI to repaint *before* the dialog blocks the event loop.
        QTimer.singleShot(50, self.launch_admin_panel_dialog)

    def launch_admin_panel_dialog(self):
        """
        This function is called by the QTimer.
        It opens the blocking AdminPanel dialog.
        """
        audio_manager.speak("Admin Panel opened.")
        self.admin_panel = AdminPanel(self.config_manager)
        self.admin_panel.exec_() # This BLOCKS until the admin panel is closed

        # --- Admin Panel is Closed: Restart Everything ---
        print("Admin Panel closed. Reloading config and restarting camera...")
        audio_manager.speak("Admin Panel closed. Restarting camera.")
        
        # Reload config in case settings were changed
        self.config = self.config_manager.load_config() 
        # Restart the recognition thread
        self.start_recognition()

    def closeEvent(self, event):
        """
        Overrides the main window's close event (e.g., clicking 'X').
        Ensures a clean shutdown.
        """
        print("Closing application...")
        audio_manager.speak("System shutting down.")
        
        # Stop the worker thread cleanly
        if hasattr(self, 'worker'):
            self.worker.stop()
            self.worker.wait() # Wait for it to finish
            
        # Shut down the audio system
        audio_manager.quit_audio() 
        event.accept() # Allow the window to close

# --- Main Application Entry Point ---
if __name__ == '__main__':
    # Import necessary modules (already imported, but good practice)
    import cv2
    import mediapipe
    
    app = QApplication(sys.argv)
    
    # Try to apply the global stylesheet to the entire app
    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        style_path = os.path.join(script_dir, "style.css")
        with open(style_path, "r") as f:
            app.setStyleSheet(f.read())
    except Exception as e:
        print(f"Could not load global stylesheet: {e}")

    # Create and show the main window
    window = MainWindow()
    window.show()
    # Start the application's event loop
    sys.exit(app.exec_())