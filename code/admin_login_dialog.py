import sys
from PyQt5.QtWidgets import (QApplication, QDialog, QWidget, QVBoxLayout, 
                             QLabel, QLineEdit, QPushButton, QMessageBox)
from PyQt5.QtCore import Qt
from config_manager import ConfigManager
import audio_manager  # Provides text-to-speech feedback

class LoginDialog(QDialog):
    """
    A modal dialog window for password authentication.
    It can be configured for two modes: 'admin' login or 'manual unlock'.
    """
    
    def __init__(self, mode='admin', parent=None):
        """
        Initializes the dialog.
        
        Args:
            mode (str): 'admin' for admin login, or any other string 
                        (e.g., 'manual') for a manual unlock prompt.
            parent (QWidget): The parent widget.
        """
        super().__init__(parent)

        # --- Load Configuration ---
        self.config_manager = ConfigManager()
        self.ADMIN_PASSWORD = self.config_manager.get('ADMIN_PASSWORD') 

        # --- Window Properties ---
        self.setModal(True)  # Block interaction with the parent window
        self.setMinimumWidth(300)
        self.setObjectName("LoginDialog")  # Used for styling

        # --- Configure Text Based on Mode ---
        if mode == 'admin':
            self.setWindowTitle("Admin Login")
            self.title_text = "Enter Admin Password"
            self.button_text = "Login"
        else:
            self.setWindowTitle("Manual Unlock")
            self.title_text = "Enter Password to Unlock"
            self.button_text = "Unlock"

        # --- Layout ---
        layout = QVBoxLayout()
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)

        # --- Widgets ---
        
        # Title Label
        self.title_label = QLabel(self.title_text)
        self.title_label.setFont(self.font())
        self.title_label.setStyleSheet("font-size: 18px; font-weight: bold;")
        self.title_label.setAlignment(Qt.AlignCenter)

        # Password Label (static text)
        self.password_label = QLabel("Password:")
        
        # Password Input (the text field)
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.Password) # Hides text as '****'
        # Connect the 'Enter' key to the login function
        self.password_input.returnPressed.connect(self.attempt_login) 

        # Login/Unlock Button
        self.login_button = QPushButton(self.button_text)
        self.login_button.clicked.connect(self.attempt_login)

        # --- Assemble Layout ---
        layout.addWidget(self.title_label)
        layout.addWidget(self.password_label)
        layout.addWidget(self.password_input)
        layout.addWidget(self.login_button)
        self.setLayout(layout)

        # This flag will be checked by the parent window
        self.login_success = False

    def attempt_login(self):
        """Checks if the entered password is correct."""
        
        entered_password = self.password_input.text()
        
        if entered_password == self.ADMIN_PASSWORD:
            # --- Success ---
            audio_manager.speak("Password OK.")  # Audio feedback
            self.login_success = True
            self.accept()  # Close the dialog and signal 'accepted'
        else:
            # --- Failure ---
            audio_manager.speak("Password failed.")  # Audio feedback
            self.login_success = False
            # Show a visual warning message
            QMessageBox.warning(self, "Failed", "Incorrect password.")
            self.password_input.clear()  # Clear the field for another try

    def was_login_successful(self):
        """
        Allows the parent window to check if the login was successful
        after the dialog closes.
        
        Returns:
            bool: True if the password was correct, False otherwise.
        """
        return self.login_success

# --- Example for running this file directly ---
if __name__ == '__main__':
    # This block is for testing the dialog independently
    app = QApplication(sys.argv)
    
    # You'll need a config.ini file with [General] ADMIN_PASSWORD=your_pass
    # and a basic audio_manager.py with a speak() function for this to run.
    
    # Test 'admin' mode
    dialog = LoginDialog(mode='admin')
    
    # .exec_() shows the dialog and waits for it to be closed
    dialog.exec_() 
    
    # After it closes, check the result
    print("Admin login was successful:", dialog.was_login_successful())

    # Test 'manual' mode
    dialog_manual = LoginDialog(mode='manual')
    dialog_manual.exec_()
    print("Manual unlock was successful:", dialog_manual.was_login_successful())

    sys.exit()