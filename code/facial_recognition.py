import cv2
import numpy as np
import os
# import pyttsx3 # <-- REMOVED
import time
import serial
import csv
from datetime import datetime
# import threading # <-- REMOVED

# -------------------- CONFIG --------------------
ARDUINO_PORT = "COM5"   
INTENT_TIME_SEC = 1.0       
LOITER_TIME_SEC = 10.0      
COUNTDOWN_SECONDS = 10      
CONFIDENCE_THRESH = 86      

# --- Paths & Logging ---
script_dir = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(script_dir, "..", "access_log.csv")
INTRUDER_FOLDER = os.path.join(script_dir, "..", "intruders")
if not os.path.exists(INTRUDER_FOLDER):
    try:
        os.makedirs(INTRUDER_FOLDER)
        print(f"Created intruders folder at: {INTRUDER_FOLDER}")
    except Exception as e:
        print(f"Error creating intruders folder: {e}")
        print("Please create the 'intruders' folder manually in the 'project' directory.")

HAARCASCADE_PATH = os.path.normpath(os.path.join(script_dir, "..", "requirements", "haarcascade_frontalface_default.xml"))
if not os.path.exists(HAARCASCADE_PATH):
    print(f"Error: Could not find haarcascade file at {HAARCASCADE_PATH}")
    print("Please download 'haarcascade_frontalface_default.xml' and place it in the 'requirements' folder.")
    exit()

# ---------------- Serial controller for Arduino ----------------
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

relay = ArduinoRelay(ARDUINO_PORT, baud=115200)

# -------------------- VOICE (FIX: Simplified to print()) --------------------
def speak(text):
    """
    This function now only prints the action to the console.
    This is 100% reliable and non-blocking.
    """
    print(f"SPEAKING: {text}")

# -------------------- LOGGING & ALARM --------------------
def log_event(event_type, username, image=None):
    """Logs an event to CSV and saves intruder image if provided."""
    timestamp = datetime.now()
    # 1. Log to CSV
    try:
        file_exists = os.path.isfile(LOG_FILE)
        with open(LOG_FILE, 'a', newline='') as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow(["Timestamp", "Event_Type", "User"]) 
            writer.writerow([timestamp.strftime("%Y-%m-%d %H:%M:%S"), event_type, username])
    except Exception as e:
        print(f"!!! Log file error: {e}")

    # 2. Save snapshot
    if image is not None and event_type == "ALERT_UNKNOWN": # Renamed event
        filename = f"ALERT_{username}_{timestamp.strftime('%Y%m%d_%H%M%S')}.jpg"
        filepath = os.path.join(INTRUDER_FOLDER, filename)
        
        try:
            cv2.imwrite(filepath, image)
            print(f"Saved alert snapshot: {filepath}")
        except Exception as e:
            print(f"!!! FAILED to save snapshot to {filepath}: {e}")

# -------------------- FACE DETECTOR --------------------
face_classifier = cv2.CascadeClassifier(HAARCASCADE_PATH)

def find_largest_face(img_gray, img_display):
    """Finds all faces and returns the ROI and bounds of the largest one."""
    faces = face_classifier.detectMultiScale(img_gray, 1.3, 5)
    if len(faces) == 0:
        return None, None
    (x, y, w, h) = max(faces, key=lambda f: f[2] * f[3])
    cv2.rectangle(img_display, (x, y), (x + w, y + h), (0, 200, 255), 2)
    roi = cv2.resize(img_gray[y:y + h, x:x + w], (200, 200))
    return roi, (x, y, w, h)

# -------------------- TRAINING --------------------
data_path = os.path.join(script_dir, "..", "face_images")
if not os.path.exists(data_path):
    print(f"Error: 'face_images' folder not found. Please run collect_facial_data.py")
    exit()

dirs = [d for d in os.listdir(data_path) if os.path.isdir(os.path.join(data_path,d))]
Training_data,Labels,names=[],[],[]
user_map = {}
for idx,user in enumerate(dirs):
    user_folder = os.path.join(data_path,user)
    names.append(user)
    user_map[idx] = user
    for file in os.listdir(user_folder):
        if file.lower().endswith('.jpg'):
            img_path = os.path.join(user_folder, file)
            img = cv2.imread(img_path, cv2.IMREAD_GRAYSCALE)
            if img is not None:
                Training_data.append(img)
                Labels.append(idx)

if len(Training_data)==0: 
    print("No training data found! Please run collect_facial_data.py to add users.")
    exit()

Labels=np.asarray(Labels,dtype=np.int32)
model=cv2.face.LBPHFaceRecognizer_create()
model.train(np.asarray(Training_data),Labels)
print(f"Training complete. Known users: {names}")

# -------------------- RECOGNITION LOOP --------------------
cap=cv2.VideoCapture(0)
time.sleep(1.0) # Wait for camera
speak("System activated.") # This will now just print

# --- State Machine Variables ---
intent_start_time = None
alert_start_time = None 
alert_triggered = False 

in_countdown = False
unlock_time = None
recognized_user = None

while True:
    ret,frame = cap.read()
    if not ret: 
        print("Camera feed lost.")
        time.sleep(1.0)
        continue

    frame_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    frame_display = frame.copy()
    
    # --- State 1: Door is Unlocked (Countdown) ---
    if in_countdown:
        elapsed = time.time() - unlock_time
        remaining = max(0, COUNTDOWN_SECONDS - int(elapsed))
        
        cv2.putText(frame_display, f"UNLOCKED", (20, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
        cv2.putText(frame_display, f"Welcome {recognized_user}", (20, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        cv2.putText(frame_display, f"Locking in {remaining}s", (20, 120), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        
        if remaining == 0:
            speak("Door locked.")
            relay.send("L")
            log_event("LOCK_AUTO", "System")
            # Reset all states
            in_countdown = False; unlock_time = None; recognized_user = None
            intent_start_time = None; alert_start_time = None; alert_triggered = False

    # --- State 2: Door is Locked (Recognition) ---
    else:
        face_roi, face_bounds = find_largest_face(frame_gray, frame_display)
        
        if face_roi is None:
            # No face detected, reset timers
            intent_start_time = None
            alert_start_time = None
            alert_triggered = False 
            
            cv2.putText(frame_display, "LOCKED", (20, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
            cv2.putText(frame_display, "Please look at camera", (20, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

        else:
            # Face detected.
            try:
                result = model.predict(face_roi)
                confidence = int((1 - result[1] / 300) * 100) # Confidence %
                user_name = user_map.get(result[0], "Unknown")

                # --- Case 1: Authorized User ---
                if confidence >= CONFIDENCE_THRESH:
                    alert_start_time = None # Not an unknown person
                    alert_triggered = False 
                    
                    if intent_start_time is None:
                        intent_start_time = time.time() # Start intent timer
                    
                    intent_elapsed = time.time() - intent_start_time
                    
                    if intent_elapsed >= INTENT_TIME_SEC:
                        # --- UNLOCK SUCCESS ---
                        speak(f"Welcome {user_name}. Door unlocked.")
                        relay.send("U")
                        log_event("UNLOCK", user_name)
                        in_countdown = True
                        unlock_time = time.time()
                        recognized_user = user_name
                    else:
                        # User is recognized, but waiting for intent
                        progress = int((intent_elapsed / INTENT_TIME_SEC) * 100)
                        cv2.putText(frame_display, f"Welcome {user_name}", (20, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
                        cv2.putText(frame_display, f"Verifying intent... {progress}%", (20, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

                # --- Case 2: Unknown User (Single Alert) ---
                else:
                    intent_start_time = None # Reset intent
                    
                    if alert_start_time is None:
                        alert_start_time = time.time()
                    
                    # Check 10-second timer and spam flag
                    if (time.time() - alert_start_time > LOITER_TIME_SEC) and not alert_triggered:
                        speak("Alert. Unknown person detected.") 
                        log_event("ALERT_UNKNOWN", "Unknown", image=frame) # Pass the full frame
                        alert_triggered = True # Set flag to prevent spam
                    
                    cv2.putText(frame_display, "ALERT: UNKNOWN", (20, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
                    cv2.putText(frame_display, f"Confidence: {confidence}%", (20, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

            except Exception as e:
                print(f"Recognition error: {e}")
                cv2.putText(frame_display, "Recognition Error", (20, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)


    # --- Display the final frame ---
    cv2.imshow("Face Recognition Security", frame_display)
    
    if cv2.waitKey(1) == 13: # Enter key to exit
        break

# --- Cleanup ---
print("Shutting down...")
speak("System shutting down.")
relay.close()
cap.release()
cv2.destroyAllWindows()