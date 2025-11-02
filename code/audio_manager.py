import pygame
import threading
from gtts import gTTS
from io import BytesIO

# --- Private Variables ---
_audio_initialized = False

def _play_task(text_to_speak):
    """
    This function runs in a separate thread to not block the UI.
    It generates the audio in memory and plays it.
    """
    try:
        # 1. Use gTTS to create an in-memory MP3
        mp3_fp = BytesIO()
        tts = gTTS(text=text_to_speak, lang='en')
        tts.write_to_fp(mp3_fp)
        mp3_fp.seek(0)
        
        # 2. Use pygame to load and play the in-memory MP3
        # We re-initialize the mixer *in the thread* for stability
        pygame.mixer.init()
        pygame.mixer.music.load(mp3_fp)
        pygame.mixer.music.play()
        
        # 3. Wait for the music to finish
        while pygame.mixer.music.get_busy():
            pygame.time.Clock().tick(10)
            
    except AssertionError:
        # This can happen if gTTS fails to connect (no internet)
        print(f"AUDIO_ERROR: Could not generate TTS for: '{text_to_speak}' (Check internet?)")
    except Exception as e:
        print(f"AUDIO_ERROR: {e}")

# --- Public Functions ---

def init_audio():
    """Call this ONCE at the start of the app."""
    global _audio_initialized
    if _audio_initialized:
        return
    try:
        # We only init the main pygame module here
        pygame.init()
        _audio_initialized = True
        print("Audio Manager Initialized.")
    except Exception as e:
        print(f"Could not initialize audio: {e}")

def speak(text):
    """
    Main audio function. Speaks text in a non-blocking thread.
    """
    if not _audio_initialized:
        print(f"SPEAK (Audio not init): {text}")
        return
    
    print(f"SPEAK: {text}") # Still print to console
    
    # Start the audio task in a new thread
    try:
        # We check if a thread is already running to avoid spamming
        # Note: This is a simple check; a more complex app might queue requests
        if threading.active_count() < 10: # Limit to 10 audio threads
            t = threading.Thread(target=_play_task, args=(text,), daemon=True)
            t.start()
        else:
            print("AUDIO_SPAM_PROTECT: Too many sounds playing.")
    except Exception as e:
        print(f"Error starting audio thread: {e}")

def quit_audio():
    """Call this ONCE when the app closes."""
    global _audio_initialized
    if _audio_initialized:
        try:
            pygame.quit()
            _audio_initialized = False
            print("Audio Manager shut down.")
        except Exception as e:
            print(f"Error quitting audio: {e}")

