"""
audio_manager.py

A non-blocking, text-to-speech (TTS) module that uses:
- gTTS (Google Text-to-Speech) to generate audio (requires internet).
- Pygame to play the audio.
- Threading to prevent the UI from freezing during audio generation and playback.
"""

import pygame
import threading
from gtts import gTTS
from io import BytesIO  # Used to handle the in-memory MP3 file

# Module-level flag to track if pygame has been initialized
_audio_initialized = False

def _play_task(text_to_speak):
    """
    This is the worker function that runs in a separate thread.
    It generates the TTS audio in memory and plays it using pygame.
    This entire function runs in the background.
    """
    try:
        # --- Step 1: Generate TTS Audio in Memory ---
        # Create an in-memory file-like object (a byte buffer)
        mp3_fp = BytesIO()
        
        # Create the gTTS object
        tts = gTTS(text=text_to_speak, lang='en')
        
        # Write the MP3 audio data directly into the in-memory buffer
        tts.write_to_fp(mp3_fp)
        
        # Rewind the buffer to the beginning so pygame can read it
        mp3_fp.seek(0)
        
        # --- Step 2: Play the Audio with Pygame ---
        # We initialize the mixer *inside the thread*
        # This is often more stable, especially in multi-threaded apps.
        pygame.mixer.init()
        
        # Load the in-memory file (mp3_fp) as music
        pygame.mixer.music.load(mp3_fp)
        pygame.mixer.music.play()
        
        # --- Step 3: Wait for Playback to Finish ---
        # This loop blocks *this thread* (not the main app)
        # until the sound has finished playing.
        while pygame.mixer.music.get_busy():
            pygame.time.Clock().tick(10)  # Check 10 times per second
            
    except AssertionError:
        # This error can occur if gTTS fails to connect to Google's
        # servers (e.g., no internet connection).
        print(f"AUDIO_ERROR: Could not generate TTS for: '{text_to_speak}' (Check internet?)")
    except Exception as e:
        # Catch any other unexpected errors (e.g., pygame mixer issues)
        print(f"AUDIO_ERROR: {e}")

# --- Public Functions ---

def init_audio():
    """
    Initializes the audio manager. 
    Call this ONCE when your application starts.
    """
    global _audio_initialized
    if _audio_initialized:
        return  # Already initialized

    try:
        # We only init the main pygame module here.
        # The mixer will be initialized in the worker thread.
        pygame.init()
        _audio_initialized = True
        print("Audio Manager Initialized.")
    except Exception as e:
        print(f"Could not initialize audio: {e}")

def speak(text):
    """
    Speaks the given text in a non-blocking background thread.
    
    Args:
        text (str): The text to be spoken.
    """
    if not _audio_initialized:
        print(f"SPEAK (Audio not init): {text}")
        return
    
    # Log the speech request to the console for debugging
    print(f"SPEAK: {text}") 
    
    try:
        # --- Simple Spam Protection ---
        # Limit the number of concurrent audio threads to prevent
        # the app from being overwhelmed.
        if threading.active_count() < 10: 
            # Start the _play_task in a new background thread
            # daemon=True means the thread won't prevent the app from exiting
            t = threading.Thread(target=_play_task, args=(text,), daemon=True)
            t.start()
        else:
            print("AUDIO_SPAM_PROTECT: Too many sounds playing.")
    except Exception as e:
        print(f"Error starting audio thread: {e}")

def quit_audio():
    """
    Shuts down the audio manager and releases pygame resources.
    Call this ONCE when your application is closing.
    """
    global _audio_initialized
    if _audio_initialized:
        try:
            pygame.quit()  # Clean up all pygame modules
            _audio_initialized = False
            print("Audio Manager shut down.")
        except Exception as e:
            print(f"Error quitting audio: {e}")