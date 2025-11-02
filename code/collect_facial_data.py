import cv2
import numpy as np
import os
import sys
import random # <-- NEW IMPORT
from config_manager import ConfigManager # <-- NEW IMPORT

# -------------------- CONFIG --------------------
script_dir = os.path.dirname(os.path.abspath(__file__))

base_path = os.path.normpath(os.path.join(script_dir, "..", "face_images"))
if not os.path.exists(base_path):
    os.makedirs(base_path)

HAARCASCADE_PATH = os.path.normpath(os.path.join(script_dir, "..", "requirements", "haarcascade_frontalface_default.xml"))

if not os.path.exists(HAARCASCADE_PATH):
    print(f"Error: Could not find haarcascade file at {HAARCASCADE_PATH}")
    print("Please download 'haarcascade_frontalface_default.xml' and place it in the 'requirements' folder.")
    exit()

# --- Load max_samples from config file ---
try:
    config_manager = ConfigManager()
    max_samples = int(config_manager.get('MAX_SAMPLES'))
except Exception as e:
    print(f"Warning: Could not load config, using default 1000 samples. Error: {e}")
    max_samples = 1000

# -------------------- FACE DETECTOR --------------------
face_classifier = cv2.CascadeClassifier(HAARCASCADE_PATH)

def face_extractor(img):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    faces = face_classifier.detectMultiScale(gray, 1.3, 5)
    if len(faces) == 0:
        return []

    (x, y, w, h) = max(faces, key=lambda f: f[2] * f[3])
    cropped_face = img[y:y+h, x:x+w]
    return [cropped_face]

# -------------------- USER INPUT --------------------
if len(sys.argv) < 2:
    print("Usage: python collect_facial_data.py <username>")
    exit()
username = sys.argv[1]

user_path = os.path.join(base_path, username)
if not os.path.exists(user_path):
    os.makedirs(user_path)
    print(f"Folder created for {username}")
else:
    print(f"User folder for {username} already exists.")

# -------------------- PRE-CAPTURE LOGIC (NEW) --------------------
cap = cv2.VideoCapture(0)
count = 0 # This will be the highest *number* (e.g., 500 from user_500.jpg)
start_count = 0 # The count before we started
current_file_count = 0 # This is the *total* number of files
new_photos_to_add = 0

try:
    # Get a list of all current jpg files
    files = [f for f in os.listdir(user_path) if f.startswith(username) and f.endswith('.jpg')]
    current_file_count = len(files)
    
    if files:
        # Find the highest number, e.g., "user_1000.jpg" -> 1000
        numbers = [int(f.split('_')[-1].split('.')[0]) for f in files]
        if numbers:
            count = max(numbers) # Start new files from this number
            start_count = count
except Exception as e:
    print(f"Could not read existing file count: {e}")

print(f"User '{username}' currently has {current_file_count} samples.")
print(f"Maximum sample limit is {max_samples}.")

# --- *** NEW "ADD FIRST" LOGIC *** ---
if current_file_count < max_samples:
    # Not at limit, so just fill up
    new_photos_to_add = max_samples - current_file_count
    print(f"Collecting {new_photos_to_add} new samples to reach the limit of {max_samples}.")
else:
    # At or over limit, start a "rolling update"
    new_photos_to_add = int(max_samples * 0.10) # Add 10%
    new_photos_to_add = max(1, new_photos_to_add) # Add at least 1
    print(f"Max samples reached. Collecting {new_photos_to_add} new samples (will replace old ones).")
# --- *** END NEW LOGIC *** ---

# -------------------- VIDEO CAPTURE --------------------
print(f"Starting collection from sample #{count + 1}.")
print("Look at the camera and press ENTER when done.")

collected_count = 0 # Counter for this session

while True:
    ret, frame = cap.read()
    if not ret:
        print("Camera not detected")
        break

    faces = face_extractor(frame)
    if not faces:
        cv2.putText(frame, "No face found", (10, 60),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
    
    for face in faces:
        # Check if we have collected enough new photos for this session
        if collected_count >= new_photos_to_add:
            break # Breaks inner loop
        
        count += 1
        collected_count += 1
        
        face_resized = cv2.resize(face, (200, 200))
        face_gray = cv2.cvtColor(face_resized, cv2.COLOR_BGR2GRAY)

        file_name_path = os.path.join(user_path, f"{username}_{count}.jpg")
        cv2.imwrite(file_name_path, face_gray)

        # Show progress for this session
        cv2.putText(face_resized, f"{collected_count}/{new_photos_to_add}", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
        cv2.imshow("Collecting Faces", face_resized)

    cv2.putText(frame, f"User: {username}", (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
    cv2.putText(frame, f"Samples added: {collected_count}/{new_photos_to_add}", (10, 60),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
    cv2.imshow("Webcam Feed", frame)

    key = cv2.waitKey(1)
    if key == 13 or collected_count >= new_photos_to_add:  # Enter key or new target
        break

cap.release()
cv2.destroyAllWindows()

# --- *** NEW POST-CAPTURE CLEANUP LOGIC *** ---
print(f"Face collection for {username} complete — {collected_count} new samples saved.")

try:
    # Get a fresh list of all files, sorted by *oldest first*
    all_files = [os.path.join(user_path, f) for f in os.listdir(user_path) if f.endswith('.jpg')]
    all_files.sort(key=os.path.getmtime)
    
    current_file_count = len(all_files)
    
    if current_file_count > max_samples:
        num_to_delete = current_file_count - max_samples
        print(f"Total files ({current_file_count}) exceed max ({max_samples}). Deleting {num_to_delete} oldest samples...")
        
        deleted_count = 0
        for i in range(num_to_delete):
            try:
                os.remove(all_files[i]) # Delete the oldest files
                deleted_count += 1
            except Exception as e_del:
                print(f"Warning: Could not delete {all_files[i]} - {e_del}")
        
        print(f"Successfully deleted {deleted_count} old samples.")
        
except Exception as e:
    print(f"Error during post-capture cleanup: {e}")

print(f"Total samples for user: {len(os.listdir(user_path))}")
# --- *** END NEW LOGIC *** ---