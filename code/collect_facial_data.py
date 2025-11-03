import cv2  # OpenCV for video capture and image processing
import numpy as np
import os
import sys
from config_manager import ConfigManager # For loading app settings

# -------------------- CONFIGURATION --------------------
script_dir = os.path.dirname(os.path.abspath(__file__))

# Path to the root folder where all user face images are stored
base_path = os.path.normpath(os.path.join(script_dir, "..", "face_images"))
if not os.path.exists(base_path):
    os.makedirs(base_path)

# Path to the Haar cascade file for face detection
HAARCASCADE_PATH = os.path.normpath(os.path.join(script_dir, "..", "requirements", "haarcascade_frontalface_default.xml"))

# --- Critical Check: Ensure the cascade file exists ---
if not os.path.exists(HAARCASCADE_PATH):
    print(f"Error: Could not find haarcascade file at {HAARCASCADE_PATH}")
    print("Please download 'haarcascade_frontalface_default.xml' and place it in the 'requirements' folder.")
    exit()

# --- Load max_samples from config file ---
try:
    config_manager = ConfigManager()
    # The total number of samples to keep per user
    max_samples = int(config_manager.get('MAX_SAMPLES'))
except Exception as e:
    print(f"Warning: Could not load config, using default 1000 samples. Error: {e}")
    max_samples = 1000

# -------------------- FACE DETECTOR --------------------
face_classifier = cv2.CascadeClassifier(HAARCASCADE_PATH)

def face_extractor(img):
    """
    Detects faces in an image and returns the largest one.
    
    Args:
        img (np.array): The input image (BGR).
    
    Returns:
        list: A list containing the cropped (BGR) face, or an empty list.
    """
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    # Detect all faces
    faces = face_classifier.detectMultiScale(gray, 1.3, 5)
    
    if len(faces) == 0:
        return [] # No face found

    # Find the largest face (based on area w*h)
    (x, y, w, h) = max(faces, key=lambda f: f[2] * f[3])
    
    # Return the cropped BGR face
    cropped_face = img[y:y+h, x:x+w]
    return [cropped_face]

# -------------------- USER & PATH SETUP --------------------
if len(sys.argv) < 2:
    print("Usage: python collect_facial_data.py <username>")
    exit()
username = sys.argv[1]

# Create the specific folder for the user (e.g., /face_images/john_doe)
user_path = os.path.join(base_path, username)
if not os.path.exists(user_path):
    os.makedirs(user_path)
    print(f"Folder created for {username}")
else:
    print(f"User folder for {username} already exists.")

# -------------------- PRE-CAPTURE ANALYSIS --------------------
cap = cv2.VideoCapture(0)

# 'count' will be the highest-numbered file index (e.g., 500 from user_500.jpg)
# This ensures new files (user_501.jpg) don't overwrite old ones.
count = 0 
start_count = 0 # The 'count' value before we started
current_file_count = 0 # The total number of .jpg files
new_photos_to_add = 0  # How many photos we will collect *this session*

try:
    # Get a list of all current jpg files for this user
    files = [f for f in os.listdir(user_path) if f.startswith(username) and f.endswith('.jpg')]
    current_file_count = len(files)
    
    if files:
        # Find the highest number to avoid overwrites
        # e.g., "user_1000.jpg" -> 1000
        numbers = [int(f.split('_')[-1].split('.')[0]) for f in files]
        if numbers:
            count = max(numbers) # Start new files from this number + 1
            start_count = count
except Exception as e:
    print(f"Could not read existing file count: {e}")

print(f"User '{username}' currently has {current_file_count} samples.")
print(f"Maximum sample limit is {max_samples}.")

# --- Determine how many new photos to collect ---
if current_file_count < max_samples:
    # Case 1: User is under the limit. Collect samples to fill the gap.
    new_photos_to_add = max_samples - current_file_count
    print(f"Collecting {new_photos_to_add} new samples to reach the limit of {max_samples}.")
else:
    # Case 2: User is at or over the limit.
    # We will add a small "rolling update" batch of new photos (10% of max).
    # The post-capture logic will then delete the *oldest* 10% to make room.
    new_photos_to_add = int(max_samples * 0.10) # Add 10%
    new_photos_to_add = max(1, new_photos_to_add) # Ensure we add at least 1
    print(f"Max samples reached. Collecting {new_photos_to_add} new samples (will replace old ones).")

# -------------------- VIDEO CAPTURE LOOP --------------------
print(f"Starting collection from sample #{count + 1}.")
print("Look at the camera and press ENTER when done.")

collected_count = 0 # Counter for *this session*

while True:
    ret, frame = cap.read()
    if not ret:
        print("Camera not detected")
        break

    faces = face_extractor(frame)
    
    if not faces:
        # No face detected, show feedback on main feed
        cv2.putText(frame, "No face found", (10, 60),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
    
    # Process the (largest) detected face
    for face in faces:
        # Check if we have collected enough new photos for this session
        if collected_count >= new_photos_to_add:
            break # Stop collecting, but keep the camera feed live
        
        count += 1             # Increment global file index (e.g., 501, 502...)
        collected_count += 1   # Increment session index (e.g., 1, 2, 3...)
        
        # --- Pre-process and Save ---
        face_resized = cv2.resize(face, (200, 200))
        face_gray = cv2.cvtColor(face_resized, cv2.COLOR_BGR2GRAY)

        file_name_path = os.path.join(user_path, f"{username}_{count}.jpg")
        cv2.imwrite(file_name_path, face_gray)

        # Show progress on the "face" window
        cv2.putText(face_resized, f"{collected_count}/{new_photos_to_add}", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
        cv2.imshow("Collecting Faces", face_resized)

    # --- Show UI on Main Feed ---
    cv2.putText(frame, f"User: {username}", (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
    cv2.putText(frame, f"Samples added: {collected_count}/{new_photos_to_add}", (10, 60),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
    cv2.imshow("Webcam Feed", frame)

    # --- Exit Conditions ---
    key = cv2.waitKey(1)
    # Stop if (Enter key is pressed) OR (we've collected the target number)
    if key == 13 or collected_count >= new_photos_to_add:
        break

cap.release()
cv2.destroyAllWindows()

# -------------------- POST-CAPTURE CLEANUP --------------------
# This logic ensures the total number of samples never exceeds 'max_samples'.
# If we went over the limit (via a "rolling update"), this will
# delete the *oldest* files to make room for the new ones.
# -------------------------------------------------------------

print(f"Face collection for {username} complete — {collected_count} new samples saved.")

try:
    # Get a fresh list of ALL files for the user
    all_files = [os.path.join(user_path, f) for f in os.listdir(user_path) if f.endswith('.jpg')]
    
    # *** CRITICAL: Sort the files by modification time, OLDEST first ***
    all_files.sort(key=os.path.getmtime)
    
    current_file_count = len(all_files)
    
    if current_file_count > max_samples:
        # We have more files than the limit, so we must delete the oldest ones
        num_to_delete = current_file_count - max_samples
        print(f"Total files ({current_file_count}) exceed max ({max_samples}). Deleting {num_to_delete} oldest samples...")
        
        deleted_count = 0
        # Iterate 'num_to_delete' times
        for i in range(num_to_delete):
            try:
                os.remove(all_files[i]) # Delete the oldest file
                deleted_count += 1
            except Exception as e_del:
                print(f"Warning: Could not delete {all_files[i]} - {e_del}")
        
        print(f"Successfully deleted {deleted_count} old samples.")
        
except Exception as e:
    print(f"Error during post-capture cleanup: {e}")

print(f"Final total samples for user: {len(os.listdir(user_path))}")