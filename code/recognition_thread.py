import cv2
import numpy as np
import os
import time
import serial
import csv
import mediapipe as mp
from datetime import datetime
from PyQt5.QtCore import QThread, pyqtSignal, pyqtSlot
import audio_manager # <-- NEW

# -------------------------------------------------------------------
# --- Arduino Relay Class ---
# -------------------------------------------------------------------
class ArduinoRelay:
    def __init__(self, port, baud=9600, timeout=0.1):
        self.port = port
        self.baud = baud
        try:
            self.ser = serial.Serial(port, baud, timeout=timeout) 
            time.sleep(2)  
            print(f"Serial port {port} @ {baud} opened successfully.")
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
            print(f"Sent to Arduino: {msg}")
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
# --- Worker Thread for Face Recognition ---
# -------------------------------------------------------------------
class RecognitionThread(QThread):
    frame_ready = pyqtSignal(np.ndarray)
    status_updated = pyqtSignal(str, str)
    info_updated = pyqtSignal(str)
    door_alert_signal = pyqtSignal(str, str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.running = True
        self.config = {}
        script_dir = os.path.dirname(os.path.abspath(__file__))
        self.log_file = os.path.join(script_dir, "..", "access_log.csv")
        self.intruder_folder = os.path.join(script_dir, "..", "intruders")
        self.haarcascade_path = os.path.normpath(os.path.join(script_dir, "..", "requirements", "haarcascade_frontalface_default.xml"))
        self.data_path = os.path.join(script_dir, "..", "face_images")
        self.model = None
        self.user_map = {}
        self.relay = None
        self.cap = None
        
        self.in_countdown = False
        self.unlock_time = None
        self.recognized_user = None
        
        self.intent_start_time = None
        self.alert_start_time = None 
        self.alert_triggered = False 
        
        self.mp_face_mesh = mp.solutions.face_mesh
        self.face_mesh = None
        self.liveness_confirmed = False
        self.blink_counter = 0
        self.required_blinks = 2
        self.eye_closed_counter = 0

    def setup(self, config, arduino_port, arduino_baud):
        self.config = config
        self.required_blinks = self.config['LIVENESS_BLINKS']
        
        self.relay = ArduinoRelay(arduino_port, arduino_baud)
        if not self.relay.ser:
            self.emit_error(f"Failed to open port {arduino_port}. Running in VIRTUAL mode.")
        else:
            timeout_sec = self.config['DOOR_AJAR_TIMEOUT']
            self.relay.send(f"T={timeout_sec}")
            print(f"Sent Door Ajar Timeout ({timeout_sec}s) to Arduino.")

        self.face_mesh = self.mp_face_mesh.FaceMesh(max_num_faces=1, 
                                                    refine_landmarks=True, 
                                                    min_detection_confidence=0.5, 
                                                    min_tracking_confidence=0.5)

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
        
    def calculate_ear(self, eye_landmarks, frame_w, frame_h):
        try:
            coords = [(int(p.x * frame_w), int(p.y * frame_h)) for p in eye_landmarks]
            p1, p2, p3, p4, p5, p6 = coords[0], coords[1], coords[2], coords[3], coords[4], coords[5]
            
            A = np.linalg.norm(np.array(p2) - np.array(p6))
            B = np.linalg.norm(np.array(p3) - np.array(p5))
            C = np.linalg.norm(np.array(p1) - np.array(p4))

            if C == 0: return 0.3
            ear = (A + B) / (2.0 * C)
            return ear
        except Exception as e:
            print(f"Error calculating EAR: {e}")
            return 0.3

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
        audio_manager.speak("System activated.") # <-- UPDATED
        
        LEFT_EYE_EAR_INDICES = [362, 385, 387, 263, 373, 380]
        RIGHT_EYE_EAR_INDICES = [33, 158, 160, 133, 144, 153]
        ALL_EYE_LANDMARKS = list(set(LEFT_EYE_EAR_INDICES + RIGHT_EYE_EAR_INDICES))

        self.liveness_confirmed = False
        self.blink_counter = 0
        self.eye_closed_counter = 0
        ear_threshold = 0.2
        ear_consec_frames = 2 

        self.intent_start_time = None
        self.alert_start_time = None 
        self.alert_triggered = False 

        while self.running:
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
            
            ret, frame = self.cap.read()
            if not ret:
                print("Camera feed lost.")
                time.sleep(1.0)
                continue
            
            frame = cv2.flip(frame, 1)
            frame_h, frame_w, _ = frame.shape
            frame_display = frame.copy()
            
            if self.in_countdown:
                elapsed = time.time() - self.unlock_time
                remaining = max(0, self.config['COUNTDOWN_SECONDS'] - int(elapsed))
                
                self.status_updated.emit("UNLOCKED", "#00FF00")
                self.info_updated.emit(f"Welcome {self.recognized_user}\n\nLocking in {remaining}s")
                
                if remaining == 0:
                    audio_manager.speak("Door locked.") # <-- UPDATED
                    self.relay.send("L")
                    self.log_event("LOCK_AUTO", "System")
                    self.in_countdown = False; self.unlock_time = None; self.recognized_user = None
                    self.intent_start_time = None; self.alert_start_time = None; self.alert_triggered = False
                    self.liveness_confirmed = False; self.blink_counter = 0
            else:
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                frame_rgb.flags.writeable = False
                results = self.face_mesh.process(frame_rgb)
                frame_rgb.flags.writeable = True

                if results.multi_face_landmarks:
                    face_landmarks = results.multi_face_landmarks[0]
                    
                    if not self.liveness_confirmed:
                        self.status_updated.emit("LOCKED", "#FF3333")
                        self.info_updated.emit(f"LIVENESS CHECK\nBlinks: {self.blink_counter} / {self.required_blinks}")

                        left_eye_pts = [face_landmarks.landmark[i] for i in LEFT_EYE_EAR_INDICES]
                        right_eye_pts = [face_landmarks.landmark[i] for i in RIGHT_EYE_EAR_INDICES]
                        
                        left_ear = self.calculate_ear(left_eye_pts, frame_w, frame_h)
                        right_ear = self.calculate_ear(right_eye_pts, frame_w, frame_h)
                        
                        ear = (left_ear + right_ear) / 2.0

                        for i in ALL_EYE_LANDMARKS:
                            pt = face_landmarks.landmark[i]
                            x = int(pt.x * frame_w)
                            y = int(pt.y * frame_h)
                            cv2.circle(frame_display, (x, y), 1, (0, 255, 0), -1)

                        if ear < ear_threshold:
                            self.eye_closed_counter += 1
                        else:
                            if self.eye_closed_counter >= ear_consec_frames:
                                self.blink_counter += 1
                                #audio_manager.speak(f"Blink {self.blink_counter} detected.") # <-- UPDATED
                            self.eye_closed_counter = 0
                        
                        if self.blink_counter >= self.required_blinks:
                            self.liveness_confirmed = True
                            audio_manager.speak("Liveness confirmed. Verifying identity.") # <-- UPDATED
                            self.intent_start_time = None
                    
                    else:
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
                            cv2.rectangle(frame_display, (x, y), (x + box_w, y + box_h), (0, 200, 255), 2)
                            
                            frame_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                            face_roi = cv2.resize(frame_gray[y:y+box_h, x:x+box_w], (200, 200))
                            
                            try:
                                result = self.model.predict(face_roi)
                                confidence = int((1 - result[1] / 300) * 100)
                                user_name = self.user_map.get(result[0], "Unknown")

                                if confidence >= self.config['CONFIDENCE_THRESH']:
                                    self.alert_start_time = None
                                    self.alert_triggered = False 
                                    
                                    if self.intent_start_time is None:
                                        self.intent_start_time = time.time()
                                    
                                    intent_elapsed = time.time() - self.intent_start_time
                                    
                                    if intent_elapsed >= self.config['INTENT_TIME_SEC']:
                                        audio_manager.speak(f"Welcome {user_name}. Door unlocked.") # <-- UPDATED
                                        self.relay.send("U")
                                        self.log_event("UNLOCK_FACE", user_name)
                                        self.in_countdown = True
                                        self.unlock_time = time.time()
                                        self.recognized_user = user_name
                                    else:
                                        self.status_updated.emit(f"Welcome {user_name}", "#00FF00")
                                        self.info_updated.emit(f"Liveness OK. Verifying intent...\n\nConfidence: {confidence}%")

                                else:
                                    self.intent_start_time = None
                                    if self.alert_start_time is None:
                                        self.alert_start_time = time.time()
                                    
                                    if (time.time() - self.alert_start_time > self.config['LOITER_TIME_SEC']) and not self.alert_triggered:
                                        audio_manager.speak("Alert. Unknown person detected.") # <-- UPDATED
                                        self.log_event("ALERT_UNKNOWN", "Unknown", image=frame)
                                        self.alert_triggered = True
                                    
                                    self.status_updated.emit("ALERT: UNKNOWN", "#FF3333")
                                    self.info_updated.emit(f"Liveness OK. Confidence: {confidence}%")

                            except Exception as e:
                                print(f"Recognition error: {e}")
                                self.status_updated.emit("ERROR", "#FF3333")
                                self.info_updated.emit("Liveness OK. Recognition error.")
                        
                        else:
                            self.status_updated.emit("LOCKED", "#FF3333")
                            self.info_updated.emit("Liveness OK. Please center your face.")
                
                else:
                    self.intent_start_time = None
                    self.alert_start_time = None
                    self.alert_triggered = False 
                    self.liveness_confirmed = False
                    self.blink_counter = 0
                    self.eye_closed_counter = 0
                    self.status_updated.emit("LOCKED", "#FF3333")
                    self.info_updated.emit("Please look at the camera.")

            self.frame_ready.emit(frame_display)
            time.sleep(0.03)
        
        print("Shutting down recognition thread...")
        if self.cap:
            self.cap.release()
        if self.relay:
            self.relay.close()
        if self.face_mesh:
            self.face_mesh.close()

    def speak(self, text):
        # This function is now just a wrapper
        audio_manager.speak(text) # <-- UPDATED

    def emit_error(self, message):
        print(f"ERROR: {message}")
        self.status_updated.emit("ERROR", "#FF3333")
        self.info_updated.emit(message)

    @pyqtSlot()
    def on_manual_unlock(self):
        if self.in_countdown:
            print("Manual unlock requested, but already in countdown.")
            return 
            
        print("Manual override: Unlocking door.")
        audio_manager.speak("Manual override. Door unlocked.") # <-- UPDATED
        self.relay.send("U")
        self.log_event("UNLOCK_MANUAL", "Admin")
        
        self.in_countdown = True
        self.unlock_time = time.time()
        self.recognized_user = "Admin Override"
        self.liveness_confirmed = False
        self.blink_counter = 0
        
    @pyqtSlot()
    def on_manual_lock(self):
        if not self.in_countdown:
            print("Manual lock requested, but already locked.")
            return
            
        print("Manual override: Locking door now.")
        audio_manager.speak("Door locked manually.") # <-- UPDATED
        self.relay.send("L")
        self.log_event("LOCK_MANUAL", "User")
        
        self.in_countdown = False
        self.unlock_time = None
        self.recognized_user = None
        self.intent_start_time = None
        self.alert_start_time = None
        self.alert_triggered = False
        self.liveness_confirmed = False
        self.blink_counter = 0

    def stop(self):
        self.running = False

