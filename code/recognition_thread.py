import cv2
import numpy as np
import os
import time
import serial
import csv
import mediapipe as mp
from datetime import datetime
from PyQt5.QtCore import QThread, pyqtSignal, pyqtSlot
import audio_manager  # Handles all text-to-speech feedback

# -------------------------------------------------------------------
# --- Arduino Relay Class ---
# -------------------------------------------------------------------
class ArduinoRelay:
    """
    Manages the serial connection and communication with the Arduino relay.
    Includes a "virtual mode" if the serial port fails to open.
    """
    def __init__(self, port, baud=9600, timeout=0.1):
        self.port = port
        self.baud = baud
        try:
            # Attempt to open the serial port
            self.ser = serial.Serial(port, baud, timeout=timeout) 
            # Wait 2 seconds for the Arduino to reset (common requirement)
            time.sleep(2)  
            print(f"Serial port {port} @ {baud} opened successfully.")
        except Exception as e:
            # --- Fallback to Virtual Mode ---
            print(f"FAILED to open serial port {port}: {e}")
            print("Running in 'NO_RELAY' mode. Door will not unlock.")
            self.ser = None

    def send(self, msg):
        """
        Sends a command string to the Arduino, appending a newline.
        In virtual mode, it just prints the command.
        """
        if not self.ser:
            print(f"VIRTUAL RELAY: {msg}") # Print to console if not connected
            return True
        try:
            # Encode the message and send it with a newline terminator
            self.ser.write((msg + '\n').encode('utf-8'))
            self.ser.flush() # Ensure the data is sent
            print(f"Sent to Arduino: {msg}")
            return True
        except Exception as e:
            print(f"Serial write error: {e}")
            return False

    def close(self):
        """
        Closes the serial port. Sends a "Lock" command first as a safety.
        """
        if self.ser:
            self.send("L") # Send a final "Lock" command
            self.ser.close()
            print("Serial port closed.")

# -------------------------------------------------------------------
# --- Worker Thread for Face Recognition ---
# -------------------------------------------------------------------
class RecognitionThread(QThread):
    """
    This is the "brains" of the operation. It runs all CV, liveness,
    and recognition logic in a background thread to keep the UI responsive.
    """
    # --- Signals for UI Updates ---
    # Emits the processed video frame
    frame_ready = pyqtSignal(np.ndarray)
    # Emits the main status (e.g., "LOCKED") and its color
    status_updated = pyqtSignal(str, str)
    # Emits secondary info (e.g., "Blinks: 1/2")
    info_updated = pyqtSignal(str)
    # Emits a signal to show a popup (e.g., "DOOR AJAR")
    door_alert_signal = pyqtSignal(str, str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        # --- State and Paths ---
        self.running = True
        self.config = {}
        script_dir = os.path.dirname(os.path.abspath(__file__))
        self.log_file = os.path.join(script_dir, "..", "access_log.csv")
        self.intruder_folder = os.path.join(script_dir, "..", "intruders")
        self.haarcascade_path = os.path.normpath(os.path.join(script_dir, "..", "requirements", "haarcascade_frontalface_default.xml"))
        self.data_path = os.path.join(script_dir, "..", "face_images")
        
        # --- Models and Hardware ---
        self.model = None    # The LBPH face recognizer
        self.user_map = {}   # Maps model IDs (0, 1, 2) to names ("john_doe")
        self.relay = None
        self.cap = None
        
        # --- State Variables ---
        self.in_countdown = False
        self.unlock_time = None
        self.recognized_user = None
        
        # Timers for intent (known user) and alert (unknown user)
        self.intent_start_time = None
        self.alert_start_time = None 
        self.alert_triggered = False 
        
        # --- Liveness Detection (Mediapipe) ---
        self.mp_face_mesh = mp.solutions.face_mesh
        self.face_mesh = None
        self.liveness_confirmed = False
        self.blink_counter = 0
        self.required_blinks = 2  # Will be set from config
        self.eye_closed_counter = 0 # Frames eye has been closed

    def setup(self, config, arduino_port, arduino_baud):
        """
        Initializes the thread. Called by the main window *before* start().
        """
        self.config = config
        self.required_blinks = self.config['LIVENESS_BLINKS']
        
        # --- Initialize Arduino ---
        self.relay = ArduinoRelay(arduino_port, arduino_baud)
        if not self.relay.ser:
            self.emit_error(f"Failed to open port {arduino_port}. Running in VIRTUAL mode.")
        else:
            # Send the "Door Ajar Timeout" config to the Arduino on startup
            timeout_sec = self.config['DOOR_AJAR_TIMEOUT']
            self.relay.send(f"T={timeout_sec}")
            print(f"Sent Door Ajar Timeout ({timeout_sec}s) to Arduino.")

        # --- Initialize Mediapipe Face Mesh ---
        self.face_mesh = self.mp_face_mesh.FaceMesh(max_num_faces=1, 
                                                   refine_landmarks=True, 
                                                   min_detection_confidence=0.5, 
                                                   min_tracking_confidence=0.5)

        # --- Train the Face Recognition Model ---
        if not self.train_model():
            # If training fails (e.g., no data), stop setup
            return False
            
        return True

    def train_model(self):
        """
        Loads all user images from the 'face_images' directory and
        trains the LBPH recognizer.
        """
        self.info_updated.emit("Loading training data...")
        if not os.path.exists(self.data_path):
            self.emit_error("Fatal: 'face_images' folder not found. Please run data collection.")
            return False

        # Get all subdirectories (each is a user)
        dirs = [d for d in os.listdir(self.data_path) if os.path.isdir(os.path.join(self.data_path,d))]
        
        Training_data, Labels = [], []
        self.user_map = {}
        
        # Build the user map (e.g., 0: 'john_doe', 1: 'jane_doe')
        for idx, user in enumerate(dirs):
            user_folder = os.path.join(self.data_path, user)
            self.user_map[idx] = user
            
            # Load all images for this user
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
        
        # Create and train the LBPH recognizer
        self.model = cv2.face.LBPHFaceRecognizer_create()
        self.model.train(np.asarray(Training_data), Labels)
        
        print(f"Training complete. Known users: {self.user_map.values()}")
        self.info_updated.emit("Training complete. System ready.")
        return True
        
    def calculate_ear(self, eye_landmarks, frame_w, frame_h):
        """
        Calculates the Eye Aspect Ratio (EAR) for liveness detection.
        EAR = (||P2-P6|| + ||P3-P5||) / (2 * ||P1-P4||)
        """
        try:
            # Convert landmark coordinates to pixel space
            coords = [(int(p.x * frame_w), int(p.y * frame_h)) for p in eye_landmarks]
            p1, p2, p3, p4, p5, p6 = coords[0], coords[1], coords[2], coords[3], coords[4], coords[5]
            
            # Calculate vertical distances
            A = np.linalg.norm(np.array(p2) - np.array(p6))
            B = np.linalg.norm(np.array(p3) - np.array(p5))
            
            # Calculate horizontal distance
            C = np.linalg.norm(np.array(p1) - np.array(p4))

            if C == 0: return 0.3 # Avoid division by zero
            
            ear = (A + B) / (2.0 * C)
            return ear
        except Exception as e:
            print(f"Error calculating EAR: {e}")
            return 0.3 # Default to "open"

    def log_event(self, event_type, username, image=None):
        """
        Logs an event to the access_log.csv file.
        If the event is an alert, it also saves a snapshot.
        """
        timestamp = datetime.now()
        
        # --- Log to CSV ---
        try:
            file_exists = os.path.isfile(self.log_file)
            with open(self.log_file, 'a', newline='') as f:
                writer = csv.writer(f)
                if not file_exists:
                    # Write header if file is new
                    writer.writerow(["Timestamp", "Event_Type", "User"]) 
                writer.writerow([timestamp.strftime("%Y-%m-%d %H:%M:%S"), event_type, username])
        except Exception as e:
            print(f"!!! Log file error: {e}")

        # --- Save Intruder Snapshot ---
        if image is not None and event_type == "ALERT_UNKNOWN":
            filename = f"ALERT_{username}_{timestamp.strftime('%Y%m%d_%H%M%S')}.jpg"
            filepath = os.path.join(self.intruder_folder, filename)
            try:
                cv2.imwrite(filepath, image)
                print(f"Saved alert snapshot: {filepath}")
            except Exception as e:
                print(f"!!! FAILED to save snapshot to {filepath}: {e}")

    def run(self):
        """The main loop for the recognition thread."""
        
        self.cap = cv2.VideoCapture(0)
        if not self.cap.isOpened():
            self.emit_error("Camera not detected.")
            self.running = False
            return

        print("Recognition thread started.")
        audio_manager.speak("System activated.") # Startup sound
        
        # --- Liveness Constants ---
        # Landmark indices for EAR calculation
        LEFT_EYE_EAR_INDICES = [362, 385, 387, 263, 373, 380]
        RIGHT_EYE_EAR_INDICES = [33, 158, 160, 133, 144, 153]
        ALL_EYE_LANDMARKS = list(set(LEFT_EYE_EAR_INDICES + RIGHT_EYE_EAR_INDICES))
        
        # Reset state variables
        self.liveness_confirmed = False
        self.blink_counter = 0
        self.eye_closed_counter = 0
        ear_threshold = 0.2       # EAR value below which an eye is "closed"
        ear_consec_frames = 2     # Frames eye must be closed to count as a "blink"

        self.intent_start_time = None
        self.alert_start_time = None 
        self.alert_triggered = False 

        while self.running:
            # --- Check for Arduino Messages (Door Ajar, etc.) ---
            if self.relay and self.relay.ser and self.relay.ser.in_waiting > 0:
                try:
                    while self.relay.ser.in_waiting > 0:
                        msg = self.relay.ser.readline().decode('utf-8', errors='ignore').strip()
                        if not msg: continue
                        
                        print(f"Arduino msg: {msg}")
                        if "ALERT:DOOR_AJAR" in msg:
                            print("Received door ajar alert from Arduino.")
                            self.door_alert_signal.emit("Door Ajar Alert", "The door has been left open for too long!")
                            self.log_event("ALERT_DOOR_AJAR", "System")
                        elif "STATUS:DOOR_CLOSED" in msg:
                            print("Door is closed.")
                            self.door_alert_signal.emit("Door Closed", "The door is now secure.")
                except Exception as e:
                    print(f"Error reading from serial: {e}")
            
            # --- Grab Frame ---
            ret, frame = self.cap.read()
            if not ret:
                print("Camera feed lost.")
                time.sleep(1.0)
                continue
            
            frame = cv2.flip(frame, 1) # Flip horizontally
            frame_h, frame_w, _ = frame.shape
            frame_display = frame.copy() # We draw on this copy
            
            # --- State 1: UNLOCKED (in countdown) ---
            if self.in_countdown:
                elapsed = time.time() - self.unlock_time
                remaining = max(0, self.config['COUNTDOWN_SECONDS'] - int(elapsed))
                
                # Update UI
                self.status_updated.emit("UNLOCKED", "#00FF00")
                self.info_updated.emit(f"Welcome {self.recognized_user}\n\nLocking in {remaining}s")
                
                # --- Relock Condition ---
                if remaining == 0:
                    audio_manager.speak("Door locked.")
                    self.relay.send("L")
                    self.log_event("LOCK_AUTO", "System")
                    # Reset all state variables
                    self.in_countdown = False; self.unlock_time = None; self.recognized_user = None
                    self.intent_start_time = None; self.alert_start_time = None; self.alert_triggered = False
                    self.liveness_confirmed = False; self.blink_counter = 0
            
            # --- State 2: LOCKED (Normal operation) ---
            else:
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                frame_rgb.flags.writeable = False # Read-only for Mediapipe
                results = self.face_mesh.process(frame_rgb)
                frame_rgb.flags.writeable = True

                # --- Face Found ---
                if results.multi_face_landmarks:
                    face_landmarks = results.multi_face_landmarks[0]
                    
                    # --- Step A: Liveness Check ---
                    if not self.liveness_confirmed:
                        self.status_updated.emit("LOCKED", "#FF3333")
                        self.info_updated.emit(f"LIVENESS CHECK\nBlinks: {self.blink_counter} / {self.required_blinks}")

                        # Get eye landmark points
                        left_eye_pts = [face_landmarks.landmark[i] for i in LEFT_EYE_EAR_INDICES]
                        right_eye_pts = [face_landmarks.landmark[i] for i in RIGHT_EYE_EAR_INDICES]
                        
                        left_ear = self.calculate_ear(left_eye_pts, frame_w, frame_h)
                        right_ear = self.calculate_ear(right_eye_pts, frame_w, frame_h)
                        ear = (left_ear + right_ear) / 2.0

                        # Draw eye landmarks for feedback
                        for i in ALL_EYE_LANDMARKS:
                            pt = face_landmarks.landmark[i]
                            x = int(pt.x * frame_w)
                            y = int(pt.y * frame_h)
                            cv2.circle(frame_display, (x, y), 1, (0, 255, 0), -1)

                        # Check for blink
                        if ear < ear_threshold:
                            self.eye_closed_counter += 1
                        else:
                            if self.eye_closed_counter >= ear_consec_frames:
                                self.blink_counter += 1
                                # Disabling audio feedback per-blink (too noisy)
                                # audio_manager.speak(f"Blink {self.blink_counter} detected.")
                            self.eye_closed_counter = 0
                        
                        if self.blink_counter >= self.required_blinks:
                            self.liveness_confirmed = True
                            audio_manager.speak("Liveness confirmed. Verifying identity.")
                            self.intent_start_time = None # Reset intent timer
                    
                    # --- Step B: Recognition (Liveness is OK) ---
                    else:
                        # Get bounding box from face mesh (more stable than Haar)
                        h, w, c = frame.shape
                        cx_min, cy_min = w, h
                        cx_max, cy_max = 0, 0
                        for lm in face_landmarks.landmark:
                            cx, cy = int(lm.x * w), int(lm.y * h)
                            if cx < cx_min: cx_min = cx
                            if cy < cy_min: cy_min = cy
                            if cx > cx_max: cx_max = cx
                            if cy > cy_max: cy_max = cy
                        
                        padding = 20
                        x = max(0, cx_min - padding)
                        y = max(0, cy_min - padding)
                        box_w = min(w - 1, cx_max + padding) - x
                        box_h = min(h - 1, cy_max + padding) - y

                        if box_w > 0 and box_h > 0:
                            # Draw bounding box
                            cv2.rectangle(frame_display, (x, y), (x + box_w, y + box_h), (0, 200, 255), 2)
                            
                            # --- Predict ---
                            frame_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                            # Crop, resize, and send to recognizer
                            face_roi = cv2.resize(frame_gray[y:y+box_h, x:x+box_w], (200, 200))
                            
                            try:
                                result = self.model.predict(face_roi)
                                # Lower distance = better match. Convert to %
                                confidence = int((1 - result[1] / 300) * 100) 
                                user_name = self.user_map.get(result[0], "Unknown")

                                # --- Case 1: Known User ---
                                if confidence >= self.config['CONFIDENCE_THRESH']:
                                    self.alert_start_time = None # Reset alert
                                    self.alert_triggered = False 
                                    
                                    if self.intent_start_time is None:
                                        self.intent_start_time = time.time()
                                    
                                    intent_elapsed = time.time() - self.intent_start_time
                                    
                                    # --- UNLOCK CONDITION ---
                                    if intent_elapsed >= self.config['INTENT_TIME_SEC']:
                                        audio_manager.speak(f"Welcome {user_name}. Door unlocked.")
                                        self.relay.send("U")
                                        self.log_event("UNLOCK_FACE", user_name)
                                        self.in_countdown = True
                                        self.unlock_time = time.time()
                                        self.recognized_user = user_name
                                    else:
                                        # Show "verifying intent"
                                        self.status_updated.emit(f"Welcome {user_name}", "#00FF00")
                                        self.info_updated.emit(f"Liveness OK. Verifying intent...\n\nConfidence: {confidence}%")

                                # --- Case 2: Unknown User ---
                                else:
                                    self.intent_start_time = None # Reset intent
                                    if self.alert_start_time is None:
                                        self.alert_start_time = time.time()
                                    
                                    # --- ALERT CONDITION ---
                                    if (time.time() - self.alert_start_time > self.config['LOITER_TIME_SEC']) and not self.alert_triggered:
                                        audio_manager.speak("Alert. Unknown person detected.")
                                        self.log_event("ALERT_UNKNOWN", "Unknown", image=frame)
                                        self.alert_triggered = True
                                    
                                    self.status_updated.emit("ALERT: UNKNOWN", "#FF3333")
                                    self.info_updated.emit(f"Liveness OK. Confidence: {confidence}%")

                            except Exception as e:
                                print(f"Recognition error: {e}")
                                self.status_updated.emit("ERROR", "#FF3333")
                                self.info_updated.emit("Liveness OK. Recognition error.")
                        
                        else: # Bounding box was invalid
                            self.status_updated.emit("LOCKED", "#FF3333")
                            self.info_updated.emit("Liveness OK. Please center your face.")
                
                # --- No Face Found ---
                else:
                    # Reset all timers and liveness
                    self.intent_start_time = None
                    self.alert_start_time = None
                    self.alert_triggered = False 
                    self.liveness_confirmed = False
                    self.blink_counter = 0
                    self.eye_closed_counter = 0
                    self.status_updated.emit("LOCKED", "#FF3333")
                    self.info_updated.emit("Please look at the camera.")

            # --- Emit the final frame to the UI ---
            self.frame_ready.emit(frame_display)
            # Small delay to keep thread from hogging CPU
            time.sleep(0.03) 
        
        # --- Cleanup (Loop has exited) ---
        print("Shutting down recognition thread...")
        if self.cap:
            self.cap.release()
        if self.relay:
            self.relay.close()
        if self.face_mesh:
            self.face_mesh.close()

    def speak(self, text):
        """
        Wrapper function to call the global audio manager.
        """
        audio_manager.speak(text) 

    def emit_error(self, message):
        """Helper function to log and emit a fatal error."""
        print(f"ERROR: {message}")
        self.status_updated.emit("ERROR", "#FF3333")
        self.info_updated.emit(message)

    # --- UI Signal Slots ---

    @pyqtSlot()
    def on_manual_unlock(self):
        """Slot to handle the 'manual_unlock_signal' from the UI."""
        if self.in_countdown:
            print("Manual unlock requested, but already in countdown.")
            return 
            
        print("Manual override: Unlocking door.")
        audio_manager.speak("Manual override. Door unlocked.")
        self.relay.send("U")
        self.log_event("UNLOCK_MANUAL", "Admin")
        
        # Start a countdown just like a normal unlock
        self.in_countdown = True
        self.unlock_time = time.time()
        self.recognized_user = "Admin Override"
        self.liveness_confirmed = False
        self.blink_counter = 0
        
    @pyqtSlot()
    def on_manual_lock(self):
        """Slot to handle the 'manual_lock_signal' from the UI."""
        if not self.in_countdown:
            print("Manual lock requested, but already locked.")
            return
            
        print("Manual override: Locking door now.")
        audio_manager.speak("Door locked manually.")
        self.relay.send("L")
        self.log_event("LOCK_MANUAL", "User")
        
        # Reset all state variables
        self.in_countdown = False
        self.unlock_time = None
        self.recognized_user = None
        self.intent_start_time = None
        self.alert_start_time = None
        self.alert_triggered = False
        self.liveness_confirmed = False
        self.blink_counter = 0

    def stop(self):
        """Sets the flag to stop the main 'run' loop."""
        self.running = False