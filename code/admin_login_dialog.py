import sys
from PyQt5.QtWidgets import (QApplication, QDialog, QWidget, QVBoxLayout, 
                             QLabel, QLineEdit, QPushButton, QMessageBox)
from PyQt5.QtCore import Qt
from config_manager import ConfigManager
import audio_manager # <-- NEW

class LoginDialog(QDialog):
    def __init__(self, mode='admin', parent=None):
        super().__init__(parent)

        self.config_manager = ConfigManager()
        self.ADMIN_PASSWORD = self.config_manager.get('ADMIN_PASSWORD') 

        self.setModal(True)
        self.setMinimumWidth(300)
        self.setObjectName("LoginDialog") 

        if mode == 'admin':
            self.setWindowTitle("Admin Login")
            self.title_text = "Enter Admin Password"
            self.button_text = "Login"
        else:
            self.setWindowTitle("Manual Unlock")
            self.title_text = "Enter Password to Unlock"
            self.button_text = "Unlock"

        # --- STYLESHEET REMOVED ---

        layout = QVBoxLayout()
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)

        self.title_label = QLabel(self.title_text)
        self.title_label.setFont(self.font())
        self.title_label.setStyleSheet("font-size: 18px; font-weight: bold;")
        self.title_label.setAlignment(Qt.AlignCenter)

        self.password_label = QLabel("Password:")
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.Password)
        self.password_input.returnPressed.connect(self.attempt_login) 

        self.login_button = QPushButton(self.button_text)
        self.login_button.clicked.connect(self.attempt_login)

        layout.addWidget(self.title_label)
        layout.addWidget(self.password_label)
        layout.addWidget(self.password_input)
        layout.addWidget(self.login_button)
        self.setLayout(layout)

        self.login_success = False

    def attempt_login(self):
        """Checks if the password is correct."""
        entered_password = self.password_input.text()
        if entered_password == self.ADMIN_PASSWORD:
            audio_manager.speak("Password OK.") # <-- NEW
            self.login_success = True
            self.accept()
        else:
            audio_manager.speak("Password failed.") # <-- NEW
            self.login_success = False
            QMessageBox.warning(self, "Failed", "Incorrect password.")
            self.password_input.clear()

    def was_login_successful(self):
        """Allows the main window to check if login was ok."""
        return self.login_success

