import cv2
import numpy as np
import os
import sys # <-- IMPORTED

# -------------------- CONFIG --------------------
script_dir = os.path.dirname(os.path.abspath(__file__))

# Path fix: Go up one level (to 'project') and then into 'face_images'
base_path = os.path.normpath(os.path.join(script_dir, "..", "face_images"))
if not os.path.exists(base_path):
    os.makedirs(base_path)

# Path fix: Go up one level and into 'requirements' for the XML
HAARCASCADE_PATH = os.path.normpath(os.path.join(script_dir, "..", "requirements", "haarcascade_frontalface_default.xml"))

if not os.path.exists(HAARCASCADE_PATH):
    print(f"Error: Could not find haarcascade file at {HAARCASCADE_PATH}")
    print("Please download 'haarcascade_frontalface_default.xml' and place it in the 'requirements' folder.")
    exit()

max_samples = 1000  # total samples to collect

# -------------------- FACE DETECTOR --------------------
face_classifier = cv2.CascadeClassifier(HAARCASCADE_PATH)

def face_extractor(img):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    # Detect faces
    faces = face_classifier.detectMultiScale(gray, 1.3, 5)
    if len(faces) == 0:
        return []

    # Find the largest face (most likely the user)
    (x, y, w, h) = max(faces, key=lambda f: f[2] * f[3])
    cropped_face = img[y:y+h, x:x+w]
    return [cropped_face] # Return as a list

# -------------------- USER INPUT (FIX) --------------------
# --- This block is new ---
if len(sys.argv) < 2:
    print("Usage: python collect_facial_data.py <username>")
    exit()
username = sys.argv[1]
# --- End of new block ---

user_path = os.path.join(base_path, username)
if not os.path.exists(user_path):
    os.makedirs(user_path)
    print(f"Folder created for {username}")
else:
    print(f"Adding more samples for {username}")

# -------------------- VIDEO CAPTURE --------------------
cap = cv2.VideoCapture(0)
count = len(os.listdir(user_path))  # continue counting if folder already exists

print("Starting data collection. Look at the camera and press ENTER when done (or if max samples are reached).")

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
        count += 1
        face_resized = cv2.resize(face, (200, 200))
        face_gray = cv2.cvtColor(face_resized, cv2.COLOR_BGR2GRAY)

        # Save image
        file_name_path = os.path.join(user_path, f"{username}_{count}.jpg")
        cv2.imwrite(file_name_path, face_gray)

        # Overlay info
        cv2.putText(face_resized, f"{username} - {count}/{max_samples}", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
        cv2.imshow("Collecting Faces", face_resized)

    # Show webcam with overall info
    cv2.putText(frame, f"User: {username}", (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
    cv2.putText(frame, f"Samples: {count}/{max_samples}", (10, 60),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
    cv2.imshow("Webcam Feed", frame)

    # Stop conditions
    key = cv2.waitKey(1)
    if key == 13 or count >= max_samples:  # Enter key or enough samples
        break

cap.release()
cv2.destroyAllWindows()
print(f"Face collection for {username} complete — {count} samples saved.")