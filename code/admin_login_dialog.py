import sys
from PyQt5.QtWidgets import (QApplication, QDialog, QWidget, QVBoxLayout, 
                             QLabel, QLineEdit, QPushButton, QMessageBox)
from PyQt5.QtCore import Qt
from config_manager import ConfigManager

class LoginDialog(QDialog):
    # --- MODIFIED: Added 'mode' parameter ---
    def __init__(self, mode='admin', parent=None):
        super().__init__(parent)

        self.config_manager = ConfigManager()
        self.ADMIN_PASSWORD = self.config_manager.get('ADMIN_PASSWORD') 

        self.setModal(True) # Blocks the main window until this is closed
        self.setMinimumWidth(300)

        # --- Set title based on mode ---
        if mode == 'admin':
            self.setWindowTitle("Admin Login")
            self.title_text = "Enter Admin Password"
            self.button_text = "Login"
        else:
            self.setWindowTitle("Manual Unlock")
            self.title_text = "Enter Password to Unlock"
            self.button_text = "Unlock"

        # --- Styling ---
        self.setStyleSheet("""
            QDialog {
                background-color: #2E2E2E;
                color: #FFFFFF;
            }
            QLabel {
                font-size: 14px;
            }
            QLineEdit {
                background-color: #555555;
                color: #FFFFFF;
                border: 1px solid #777777;
                border-radius: 5px;
                padding: 5px;
                font-size: 14px;
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
        """)

        # --- Layout and Widgets ---
        layout = QVBoxLayout()
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)

        self.title_label = QLabel(self.title_text) # Use dynamic title
        self.title_label.setFont(self.font())
        self.title_label.setStyleSheet("font-size: 18px; font-weight: bold;")
        self.title_label.setAlignment(Qt.AlignCenter)

        self.password_label = QLabel("Password:")
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.Password)
        self.password_input.returnPressed.connect(self.attempt_login) 

        self.login_button = QPushButton(self.button_text) # Use dynamic text
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
            print("Password OK.")
            self.login_success = True
            self.accept() # Closes the dialog and returns "True"
        else:
            print("Password failed.")
            self.login_success = False
            QMessageBox.warning(self, "Failed", "Incorrect password.")
            self.password_input.clear() # Clear the text field

    def was_login_successful(self):
        """Allows the main window to check if login was ok."""
        return self.login_success

# --- For testing this file directly ---
if __name__ == '__main__':
    app = QApplication(sys.argv)
    
    print("Testing Admin Mode:")
    dialog_admin = LoginDialog(mode='admin')
    dialog_admin.exec_()
    print(f"Login success: {dialog_admin.was_login_successful()}")

    print("Testing Unlock Mode:")
    dialog_unlock = LoginDialog(mode='unlock')
    dialog_unlock.exec_()
    print(f"Login success: {dialog_unlock.was_login_successful()}")