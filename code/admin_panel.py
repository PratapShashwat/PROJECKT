import sys
import os
import subprocess
import shutil
import csv
from datetime import datetime, timedelta # <-- NEW IMPORTS
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QTabWidget, QWidget, QFormLayout, 
                             QLabel, QLineEdit, QPushButton, QSlider, QMessageBox,
                             QHBoxLayout, QSpacerItem, QSizePolicy, QListWidget, QListWidgetItem,
                             QTableWidget, QTableWidgetItem, QHeaderView, QScrollArea, QGridLayout)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap
from config_manager import ConfigManager

class AdminPanel(QDialog):
    
    def __init__(self, config_manager, parent=None):
        super().__init__(parent)

        self.config_manager = config_manager
        self.config = self.config_manager.get_all()
        
        # --- Paths for data management ---
        script_dir = os.path.dirname(os.path.abspath(__file__))
        self.data_path = os.path.normpath(os.path.join(script_dir, "..", "face_images"))
        self.log_file_path = os.path.normpath(os.path.join(script_dir, "..", "access_log.csv"))
        self.intruder_folder_path = os.path.normpath(os.path.join(script_dir, "..", "intruders"))
        
        # --- *** NEW: Perform cleanup *before* loading tabs *** ---
        self.perform_cleanup() 
        
        self.setWindowTitle("Admin Panel")
        self.setModal(True)
        self.setMinimumSize(600, 500) 

        # --- Styling (unchanged) ---
        self.setStyleSheet("""
            QDialog {
                background-color: #2E2E2E;
                color: #FFFFFF;
            }
            QTabWidget::pane {
                border-top: 2px solid #555555;
            }
            QTabBar::tab {
                background: #444444;
                color: #FFFFFF;
                padding: 10px;
                border: 1px solid #555555;
                border-bottom: none;
                border-top-left-radius: 5px;
                border-top-right-radius: 5px;
            }
            QTabBar::tab:selected {
                background: #2E2E2E;
                border-bottom: 2px solid #007ACC;
            }
            QWidget#Tab {
                background-color: #2E2E2E;
            }
            QSlider::groove:horizontal {
                border: 1px solid #999999;
                height: 8px; 
                background: #555555;
                margin: 2px 0;
                border-radius: 4px;
            }
            QSlider::handle:horizontal {
                background: #007ACC;
                border: 1px solid #007ACC;
                width: 18px;
                margin: -5px 0; 
                border-radius: 9px;
            }
            QLineEdit {
                background-color: #555555;
                color: #FFFFFF;
                border: 1px solid #777777;
                border-radius: 5px;
                padding: 5px;
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
            QPushButton#DeleteButton {
                background-color: #D32F2F;
            }
            QPushButton#DeleteButton:hover {
                background-color: #B71C1C;
            }
            QListWidget {
                background-color: #444444;
                border: 1px solid #777777;
                border-radius: 5px;
            }
            QTableWidget { 
                background-color: #444444; 
                gridline-color: #555555; 
            }
            QHeaderView::section { 
                background-color: #555555; 
                color: #FFFFFF; 
                padding: 4px; 
                border: 1px solid #333333; 
            }
        """)

        # --- Main Layout & Tab Widget ---
        main_layout = QVBoxLayout()
        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs)
        self.setLayout(main_layout)

        # --- Create Tabs ---
        self.create_settings_tab()
        self.create_user_mgmt_tab()
        self.create_logs_tab()
        self.create_intruders_tab()
        
        # Populate lists *after* cleanup
        self.populate_user_list()
        self.populate_log_table() 
        self.populate_intruder_photos()

    # --- *** NEW FUNCTION *** ---
    def perform_cleanup(self):
        """Deletes old logs and intruder photos."""
        print("Performing data cleanup...")
        now = datetime.now()
        
        # 1. Clean Access Log (older than 7 days)
        log_cutoff = now - timedelta(days=7)
        valid_log_rows = []
        try:
            if os.path.exists(self.log_file_path):
                with open(self.log_file_path, 'r', newline='') as f:
                    reader = csv.reader(f)
                    header = next(reader, None) # Get header
                    if header:
                        valid_log_rows.append(header)
                    
                    for row in reader:
                        if len(row) >= 1:
                            try:
                                # Row timestamps are in format: 2025-10-31 11:52:03
                                row_date = datetime.strptime(row[0], "%Y-%m-%d %H:%M:%S")
                                if row_date >= log_cutoff:
                                    valid_log_rows.append(row)
                            except ValueError:
                                # Keep malformed rows just in case, or if they are old
                                if now.strptime(row[0], "%Y-%m-%d %H:%M:%S") >= log_cutoff:
                                    valid_log_rows.append(row)
                
                # Rewrite the file with only the valid rows
                with open(self.log_file_path, 'w', newline='') as f:
                    writer = csv.writer(f)
                    writer.writerows(valid_log_rows)
                print(f"Access log cleanup complete. {len(valid_log_rows)-1} entries remain.")
            else:
                print("Access log not found, skipping cleanup.")

        except Exception as e:
            print(f"Error cleaning access log: {e}")

        # 2. Clean Intruder Photos (older than 30 days)
        photo_cutoff = (now - timedelta(days=30)).timestamp()
        try:
            if os.path.exists(self.intruder_folder_path):
                count_deleted = 0
                for filename in os.listdir(self.intruder_folder_path):
                    filepath = os.path.join(self.intruder_folder_path, filename)
                    if os.path.isfile(filepath):
                        try:
                            file_mod_time = os.path.getmtime(filepath)
                            if file_mod_time < photo_cutoff:
                                os.remove(filepath)
                                count_deleted += 1
                        except Exception as e_file:
                            print(f"Could not process file {filepath}: {e_file}")
                print(f"Intruder photo cleanup complete. {count_deleted} files deleted.")
            else:
                print("Intruder folder not found, skipping cleanup.")
        except Exception as e:
            print(f"Error cleaning intruder photos: {e}")

    def create_settings_tab(self):
        """Creates the 'Settings' tab with all its widgets."""
        tab = QWidget()
        tab.setObjectName("Tab")
        layout = QVBoxLayout()
        
        form_layout = QFormLayout()
        form_layout.setSpacing(15)

        # --- Create Widgets ---
        self.port_input = QLineEdit(self.config_manager.get('ARDUINO_PORT'))
        
        self.intent_slider = QSlider(Qt.Horizontal)
        self.intent_slider.setRange(1, 50) # 0.1s to 5.0s
        self.intent_slider.setValue(int(self.config_manager.get('INTENT_TIME_SEC') * 10))
        self.intent_label = QLabel(f"{self.intent_slider.value() / 10.0:.1f} s")
        self.intent_slider.valueChanged.connect(lambda v: self.intent_label.setText(f"{v / 10.0:.1f} s"))

        self.alert_slider = QSlider(Qt.Horizontal)
        self.alert_slider.setRange(5, 30) # 5s to 30s
        self.alert_slider.setValue(int(self.config_manager.get('LOITER_TIME_SEC')))
        self.alert_label = QLabel(f"{self.alert_slider.value()} s")
        self.alert_slider.valueChanged.connect(lambda v: self.alert_label.setText(f"{v} s"))

        self.countdown_slider = QSlider(Qt.Horizontal)
        self.countdown_slider.setRange(5, 60) # 5s to 60s
        self.countdown_slider.setValue(int(self.config_manager.get('COUNTDOWN_SECONDS')))
        self.countdown_label = QLabel(f"{self.countdown_slider.value()} s")
        self.countdown_slider.valueChanged.connect(lambda v: self.countdown_label.setText(f"{v} s"))

        self.confidence_slider = QSlider(Qt.Horizontal)
        self.confidence_slider.setRange(75, 95) # 75% to 95%
        self.confidence_slider.setValue(int(self.config_manager.get('CONFIDENCE_THRESH')))
        self.confidence_label = QLabel(f"{self.confidence_slider.value()}%")
        self.confidence_slider.valueChanged.connect(lambda v: self.confidence_label.setText(f"{v}%"))

        self.password_input = QLineEdit(self.config_manager.get('ADMIN_PASSWORD'))
        self.password_input.setEchoMode(QLineEdit.Password)
        
        self.save_button = QPushButton("Save Settings")
        self.save_button.clicked.connect(self.save_settings)

        # --- Add widgets to form ---
        form_layout.addRow(QLabel("Arduino Port:"), self.port_input)
        form_layout.addRow(QLabel("Intent Time (stare):"), self.create_slider_layout(self.intent_slider, self.intent_label))
        form_layout.addRow(QLabel("Alert Time (unknown):"), self.create_slider_layout(self.alert_slider, self.alert_label))
        form_layout.addRow(QLabel("Unlock Countdown:"), self.create_slider_layout(self.countdown_slider, self.countdown_label))
        form_layout.addRow(QLabel("Confidence Threshold:"), self.create_slider_layout(self.confidence_slider, self.confidence_label))
        form_layout.addRow(QLabel("Admin Password:"), self.password_input)
        
        layout.addLayout(form_layout)
        layout.addStretch()
        layout.addWidget(self.save_button, 0, Qt.AlignRight)
        tab.setLayout(layout)
        self.tabs.addTab(tab, "Settings")

    def create_slider_layout(self, slider, label):
        """Helper function to create a horizontal layout for a slider and its value label."""
        layout = QHBoxLayout()
        layout.addWidget(slider)
        label.setFixedWidth(50) # Keep the label at a fixed width
        layout.addWidget(label)
        widget = QWidget()
        widget.setLayout(layout)
        return widget

    def save_settings(self):
        """Saves all settings from the form to the config file."""
        try:
            self.config_manager.update('ARDUINO_PORT', self.port_input.text())
            self.config_manager.update('INTENT_TIME_SEC', self.intent_slider.value() / 10.0)
            self.config_manager.update('LOITER_TIME_SEC', self.alert_slider.value())
            self.config_manager.update('COUNTDOWN_SECONDS', self.countdown_slider.value())
            self.config_manager.update('CONFIDENCE_THRESH', self.confidence_slider.value())
            self.config_manager.update('ADMIN_PASSWORD', self.password_input.text())
            
            QMessageBox.information(self, "Success", "Settings saved successfully.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save settings: {e}")

    def create_user_mgmt_tab(self):
        """Creates the 'User Management' tab with add, view, and delete."""
        tab = QWidget()
        tab.setObjectName("Tab")
        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # --- Section 1: Add New User ---
        add_user_label = QLabel("Add New User")
        add_user_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        
        add_user_form = QFormLayout()
        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("Enter name (e.g., john_doe)")
        self.add_user_button = QPushButton("Start Data Collection")
        self.add_user_button.clicked.connect(self.run_data_collection)
        
        add_user_form.addRow(QLabel("Username:"), self.username_input)
        add_user_form.addRow(self.add_user_button)

        # --- Section 2: Manage Existing Users ---
        manage_users_label = QLabel("Manage Existing Users")
        manage_users_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        
        self.user_list = QListWidget()
        self.user_list.setFixedHeight(150)
        
        button_layout = QHBoxLayout()
        self.refresh_users_button = QPushButton("Refresh List")
        self.refresh_users_button.clicked.connect(self.populate_user_list)
        
        self.delete_user_button = QPushButton("Delete Selected User")
        self.delete_user_button.setObjectName("DeleteButton")
        self.delete_user_button.clicked.connect(self.delete_selected_user)
        
        button_layout.addWidget(self.refresh_users_button)
        button_layout.addWidget(self.delete_user_button)

        # --- Section 3: Retrain Model ---
        retrain_label = QLabel("Retrain Model")
        retrain_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        retrain_info_label = QLabel("The model will be retrained with any changes when you close the Admin Panel.")
        retrain_info_label.setWordWrap(True)

        # --- Add widgets to layout ---
        layout.addWidget(add_user_label)
        layout.addLayout(add_user_form)
        layout.addSpacerItem(QSpacerItem(20, 20, QSizePolicy.Minimum, QSizePolicy.Fixed))
        layout.addWidget(manage_users_label)
        layout.addWidget(self.user_list)
        layout.addLayout(button_layout)
        layout.addSpacerItem(QSpacerItem(20, 20, QSizePolicy.Minimum, QSizePolicy.Expanding))
        layout.addWidget(retrain_label)
        layout.addWidget(retrain_info_label)

        tab.setLayout(layout)
        self.tabs.addTab(tab, "User Management")

    def run_data_collection(self):
        """Runs the 'collect_facial_data.py' script as a separate, blocking process."""
        username = self.username_input.text().strip()
        if not username or " " in username: 
            QMessageBox.warning(self, "Error", "Username cannot be empty or contain spaces.")
            return

        try:
            python_executable = sys.executable
            script_path = os.path.normpath(os.path.join(os.path.dirname(__file__), "collect_facial_data.py"))
            
            if not os.path.exists(script_path):
                QMessageBox.critical(self, "Error", f"Script not found: {script_path}")
                return

            QMessageBox.information(self, "Starting Data Collection", 
                                    "The data collection script will now open in a new window.\n\n"
                                    "The Admin Panel will be unresponsive until you are finished.\n\n"
                                    "When done, press 'Enter' in the camera window to close it.")

            result = subprocess.run([python_executable, script_path, username], capture_output=True, text=True, check=True)
            
            print("Script output:", result.stdout)
            QMessageBox.information(self, "Success", 
                                    f"Data collection for '{username}' complete.\n\n"
                                    "The model will be retrained when you close the Admin Panel.")
            self.username_input.clear()
            self.populate_user_list() # Refresh the list
            
        except subprocess.CalledProcessError as e:
            print("Script error:", e.stderr)
            QMessageBox.critical(self, "Error", f"Script failed:\n{e.stderr}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to run script: {e}")
        finally:
            pass # No longer hiding/showing

    def populate_user_list(self):
        """Reads the 'face_images' directory and populates the QListWidget."""
        try:
            self.user_list.clear()
            if not os.path.exists(self.data_path):
                self.user_list.addItem("('face_images' folder not found)")
                return
                
            dirs = [d for d in os.listdir(self.data_path) if os.path.isdir(os.path.join(self.data_path, d))]
            if not dirs:
                self.user_list.addItem("(No users found)")
            
            for user in sorted(dirs):
                self.user_list.addItem(QListWidgetItem(user))
        except Exception as e:
            print(f"Error populating user list: {e}")

    def delete_selected_user(self):
        """Deletes the selected user's data directory."""
        current_item = self.user_list.currentItem()
        if not current_item:
            QMessageBox.warning(self, "No User Selected", "Please select a user from the list to delete.")
            return
            
        username = current_item.text()
        if username.startswith("("): # Ignore placeholder text
            return

        reply = QMessageBox.question(self, "Confirm Delete", 
                                     f"Are you sure you want to permanently delete all data for '{username}'?\nThis cannot be undone.",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)

        if reply == QMessageBox.Yes:
            try:
                user_path = os.path.join(self.data_path, username)
                shutil.rmtree(user_path)
                self.populate_user_list() # Refresh the list
                QMessageBox.information(self, "Success", f"User '{username}' has been deleted.")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to delete user: {e}")

    def create_logs_tab(self):
        """Creates the 'Access Log' tab with a table viewer."""
        tab = QWidget()
        tab.setObjectName("Tab")
        layout = QVBoxLayout()
        layout.setContentsMargins(10, 10, 10, 10)

        # --- Create Table Widget ---
        self.log_table = QTableWidget()
        self.log_table.setColumnCount(3)
        self.log_table.setHorizontalHeaderLabels(["Timestamp", "Event Type", "User"])
        self.log_table.setEditTriggers(QTableWidget.NoEditTriggers) # Make read-only
        self.log_table.setAlternatingRowColors(True) # Makes it easier to read
        self.log_table.setStyleSheet("""
            QTableWidget { 
                background-color: #444444; 
                gridline-color: #555555; 
            }
            QHeaderView::section { 
                background-color: #555555; 
                color: #FFFFFF; 
                padding: 4px; 
                border: 1px solid #333333; 
            }
        """)
        
        # --- Make columns stretch to fill window ---
        header = self.log_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        
        # --- Refresh Button ---
        self.refresh_log_button = QPushButton("Refresh Log")
        self.refresh_log_button.clicked.connect(self.populate_log_table)

        layout.addWidget(self.refresh_log_button)
        layout.addWidget(self.log_table)
        tab.setLayout(layout)
        self.tabs.addTab(tab, "Access Log")

    def populate_log_table(self):
        """Reads the access_log.csv and populates the table."""
        self.log_table.setRowCount(0) # Clear the table
        
        try:
            if not os.path.exists(self.log_file_path):
                self.log_table.setRowCount(1)
                self.log_table.setItem(0, 0, QTableWidgetItem("access_log.csv not found."))
                return

            with open(self.log_file_path, 'r', newline='') as f:
                reader = csv.reader(f)
                header = next(reader, None) # Skip header row
                
                if not header: # Handle empty file
                    return

                rows = list(reader) # Read all rows
                rows.reverse() # Show newest logs first
                
                self.log_table.setRowCount(len(rows))
                for row_idx, row in enumerate(rows):
                    if len(row) == 3: # Ensure row is not malformed
                        self.log_table.setItem(row_idx, 0, QTableWidgetItem(row[0])) # Timestamp
                        self.log_table.setItem(row_idx, 1, QTableWidgetItem(row[1])) # Event
                        self.log_table.setItem(row_idx, 2, QTableWidgetItem(row[2])) # User

        except Exception as e:
            self.log_table.setRowCount(1)
            self.log_table.setItem(0, 0, QTableWidgetItem(f"Error reading log: {e}"))

    def create_intruders_tab(self):
        """Creates the 'Intruder Photos' tab with a scrollable image gallery."""
        tab = QWidget()
        tab.setObjectName("Tab")
        layout = QVBoxLayout()
        layout.setContentsMargins(10, 10, 10, 10)

        # --- Refresh Button ---
        self.refresh_photos_button = QPushButton("Refresh Photos")
        self.refresh_photos_button.clicked.connect(self.populate_intruder_photos)
        layout.addWidget(self.refresh_photos_button)

        # --- Scroll Area ---
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("background-color: #444444; border: 1px solid #555555;")

        # --- Gallery Container Widget ---
        # This widget will sit inside the scroll area and hold the grid
        self.gallery_widget = QWidget()
        self.gallery_layout = QGridLayout() # Grid layout for photos
        self.gallery_layout.setSpacing(10)
        self.gallery_widget.setLayout(self.gallery_layout)

        self.scroll_area.setWidget(self.gallery_widget)
        layout.addWidget(self.scroll_area)
        tab.setLayout(layout)
        self.tabs.addTab(tab, "Intruder Photos")

    def populate_intruder_photos(self):
        """Scans the intruder folder and displays photos in the gallery."""
        # Clear existing photos from the grid
        for i in reversed(range(self.gallery_layout.count())): 
            widget = self.gallery_layout.itemAt(i).widget()
            if widget is not None:
                widget.deleteLater()

        try:
            if not os.path.exists(self.intruder_folder_path):
                self.gallery_layout.addWidget(QLabel("Intruder folder not found."), 0, 0)
                return

            # Get all image files, sorted by newest first
            files = [f for f in os.listdir(self.intruder_folder_path) if f.lower().endswith(('.jpg', '.png'))]
            files.sort(key=lambda f: os.path.getmtime(os.path.join(self.intruder_folder_path, f)), reverse=True)

            if not files:
                self.gallery_layout.addWidget(QLabel("No intruder photos found."), 0, 0)
                return

            # Add photos to the grid
            col_count = 3 # Number of photos per row
            for idx, filename in enumerate(files):
                filepath = os.path.join(self.intruder_folder_path, filename)

                # Create a widget for each photo
                photo_widget = QWidget()
                photo_layout = QVBoxLayout()

                # Image label
                img_label = QLabel()
                pixmap = QPixmap(filepath)
                # Scale image to a thumbnail
                img_label.setPixmap(pixmap.scaled(200, 200, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                img_label.setAlignment(Qt.AlignCenter)

                # Filename label
                file_label = QLabel(filename)
                file_label.setAlignment(Qt.AlignCenter)
                file_label.setWordWrap(True)

                photo_layout.addWidget(img_label)
                photo_layout.addWidget(file_label)
                photo_widget.setLayout(photo_layout)

                # Add the photo widget to the grid
                row = idx // col_count
                col = idx % col_count
                self.gallery_layout.addWidget(photo_widget, row, col)

        except Exception as e:
            self.gallery_layout.addWidget(QLabel(f"Error loading photos: {e}"), 0, 0)