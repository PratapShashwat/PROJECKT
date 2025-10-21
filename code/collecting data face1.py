import cv2
import numpy as np
import os

# -------------------- CONFIG --------------------
script_dir = os.path.dirname(os.path.abspath(__file__))  # folder of this script
base_path = os.path.normpath(os.path.join(script_dir, "..", "face_images"))

max_samples = 500  # total samples to collect

# -------------------- FACE DETECTOR --------------------
face_classifier = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')

def face_extractor(img):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    faces = face_classifier.detectMultiScale(gray, 1.3, 5)
    if len(faces) == 0:
        return []
    cropped_faces = []
    for (x, y, w, h) in faces:
        cropped_face = img[y:y+h, x:x+w]
        cropped_faces.append(cropped_face)
    return cropped_faces

# -------------------- USER INPUT --------------------
username = input("Enter the username: ").strip()
user_path = os.path.join(base_path, username)
if not os.path.exists(user_path):
    os.makedirs(user_path)
    print(f"Folder created for {username}")
else:
    print(f"Adding more samples for {username}")

# -------------------- VIDEO CAPTURE --------------------
cap = cv2.VideoCapture(0)
count = len(os.listdir(user_path))  # continue counting if folder already exists

while True:
    ret, frame = cap.read()
    if not ret:
        print("Camera not detected")
        break

    faces = face_extractor(frame)
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
