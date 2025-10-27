import cv2
import numpy as np
import os
import pyttsx3
import time

# -------------------- VOICE --------------------
engine = pyttsx3.init('sapi5')
voices = engine.getProperty('voices')
engine.setProperty("voice", voices[0].id)
engine.setProperty("rate", 140)
engine.setProperty("volume", 1.0)
def speak(text):
    engine.say(text)
    engine.runAndWait()

# -------------------- FACE DETECTOR --------------------
face_classifier = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
def face_detector(img):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    faces = face_classifier.detectMultiScale(gray, 1.3, 5)
    if len(faces) == 0: return img,None
    x,y,w,h = faces[0]
    cv2.rectangle(img,(x,y),(x+w,y+h),(0,200,255),2)
    roi = cv2.resize(gray[y:y+h,x:x+w],(200,200))
    return img,roi

# -------------------- TRAINING --------------------
script_dir = os.path.dirname(os.path.abspath(__file__))
data_path = os.path.join(script_dir, "..", "face_images")
data_path = os.path.normpath(data_path)
dirs = [d for d in os.listdir(data_path) if os.path.isdir(os.path.join(data_path,d))]
Training_data,Labels,names=[],[],[]
for idx,user in enumerate(dirs):
    user_folder = os.path.join(data_path,user)
    for file in os.listdir(user_folder):
        if file.lower().endswith('.jpg'):
            img = cv2.imread(os.path.join(user_folder,file),cv2.IMREAD_GRAYSCALE)
            if img is not None:
                Training_data.append(cv2.resize(img,(200,200)))
                Labels.append(idx)
    names.append(user)
if len(Training_data)==0: raise Exception("No training data found!")
Labels=np.asarray(Labels,dtype=np.int32)
model=cv2.face.LBPHFaceRecognizer_create()
model.train(np.asarray(Training_data),Labels)
print("Training complete for users:",names)
speak("Face recognition system ready.")

# -------------------- PANEL HELPERS --------------------
def draw_text_center_panel(img,text,y,panel_pos,panel_size,font_scale=0.6,color=(255,255,255),thick=2):
    x_panel, w_panel = panel_pos[0], panel_size[0]
    (w,h),_ = cv2.getTextSize(text,cv2.FONT_HERSHEY_SIMPLEX,font_scale,thick)
    x = x_panel + w_panel//2 - w//2
    cv2.putText(img,text,(x,y),cv2.FONT_HERSHEY_SIMPLEX,font_scale,color,thick)

def draw_rounded_rect(img,pos,size,color,radius=15,alpha=0.85):
    x,y = pos
    w,h = size
    overlay = img.copy()
    # corners
    cv2.circle(overlay,(x+radius,y+radius),radius,color,-1)
    cv2.circle(overlay,(x+w-radius,y+radius),radius,color,-1)
    cv2.circle(overlay,(x+radius,y+h-radius),radius,color,-1)
    cv2.circle(overlay,(x+w-radius,y+h-radius),radius,color,-1)
    # rectangles
    cv2.rectangle(overlay,(x+radius,y),(x+w-radius,y+h),color,-1)
    cv2.rectangle(overlay,(x,y+radius),(x+w,y+h-radius),color,-1)
    cv2.addWeighted(overlay,alpha,img,1-alpha,0,img)

def draw_progress(img,pos,size,progress,fg=(0,200,200),bg=(80,80,80)):
    x,y = pos
    w,h = size
    overlay = img.copy()
    cv2.rectangle(overlay,(x,y),(x+w,y+h),bg,-1)
    cv2.rectangle(overlay,(x,y),(x+int(w*progress),y+h),fg,-1)
    cv2.addWeighted(overlay,0.85,img,1-0.85,0,img)

# -------------------- RECOGNITION --------------------
cap=cv2.VideoCapture(0)
unlock_time=None;in_countdown=False;COUNTDOWN_SECONDS=10;recognized_user=None;last_face_id=None

# panel dimensions
panel_pos = (20,20)
panel_size = (300,120)

while True:
    ret,frame = cap.read()
    if not ret: continue
    image,face = face_detector(frame)

    # --- draw panel ---
    draw_rounded_rect(image,panel_pos,panel_size,(50,50,50),radius=20,alpha=0.85)

    status_text="Face not found"; color=(255,255,255)
    confidence_text=""

    if in_countdown:
        elapsed = time.time()-unlock_time
        remaining = max(0,COUNTDOWN_SECONDS-int(elapsed))
        progress = remaining/COUNTDOWN_SECONDS
        color = (0,200,200) if remaining>3 else (255,0,0)
        status_text=f"Unlocked: {recognized_user}"
        confidence_text=f"Door locks in {remaining}s"
        draw_progress(image,(panel_pos[0]+50,panel_pos[1]+90),(200,12),progress)
        if remaining==0: in_countdown=False;unlock_time=None;recognized_user=None;last_face_id=None;speak("Door locked again for your safety.")
    elif face is not None:
        try:
            result = model.predict(face)
            confidence=int((1-result[1]/300)*100)
            user_name = names[result[0]] if 0<=result[0]<len(names) else "Unknown"
            confidence_text=f"Confidence: {confidence}%"
            if confidence>=88 and last_face_id!=result[0]:
                recognized_user=user_name;unlock_time=time.time();in_countdown=True;last_face_id=result[0]
                speak(f"Face recognized. Welcome {user_name}. Door unlocked. It will lock in {COUNTDOWN_SECONDS} seconds.")
                status_text=f"Unlocked: {recognized_user}"
            else:
                status_text="Locked"; color=(255,0,0)
        except: status_text="Error reading face"; color=(255,0,0)

    # draw text centered in panel
    draw_text_center_panel(image,status_text,50,panel_pos,panel_size,font_scale=0.7,color=color)
    draw_text_center_panel(image,confidence_text,85,panel_pos,panel_size,font_scale=0.6,color=(255,255,255))

    cv2.imshow("Face Recognition",image)
    if cv2.waitKey(1)==13: break

cap.release()
cv2.destroyAllWindows()
