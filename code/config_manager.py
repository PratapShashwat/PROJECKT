import json
import os

class ConfigManager:
    """
    Handles loading, managing, and saving application settings from a JSON file.
    
    This class ensures a 'config.json' file exists. If not, it creates one
    with default values. It also automatically adds new default keys to
    an existing config file if they are missing.
    """
    
    def __init__(self, config_file='config.json'):
        """
        Initializes the ConfigManager, defines defaults, and loads the config.
        
        Args:
            config_file (str): The name of the config file to manage.
        """
        # Define the path to the config file (e.g., in the project's root)
        # It assumes this script is in a subdirectory (like 'src')
        script_dir = os.path.dirname(os.path.abspath(__file__))
        self.config_path = os.path.normpath(os.path.join(script_dir, "..", config_file))
        
        # Define the default settings for the application
        # These are used if the config file is missing or a key is missing.
        self.defaults = {
            'ARDUINO_PORT': "COM5",
            'ARDUINO_BAUD': 9600,
            'INTENT_TIME_SEC': 1.0,     # Time user must stare at camera
            'LOITER_TIME_SEC': 10.0,    # Time an unknown person can be present
            'COUNTDOWN_SECONDS': 10,    # Unlock duration
            'CONFIDENCE_THRESH': 86,    # Face recognition confidence
            'ADMIN_PASSWORD': "admin",
            'DOOR_AJAR_TIMEOUT': 20,    # Seconds until door-ajar alert
            'LIVENESS_BLINKS': 2,       # Required blinks for liveness check
            'MAX_SAMPLES': 1000,        # Max face samples per user
        }
        
        # Load the configuration on initialization
        self.config = self.load_config()

    def load_config(self):
        """
        Loads the config from the JSON file.
        
        If the file doesn't exist, it's created with defaults.
        If the file exists but is missing keys, the missing keys are added
        from 'self.defaults' and the file is updated.
        
        Returns:
            dict: The loaded and verified configuration dictionary.
        """
        # Case 1: Config file does not exist
        if not os.path.exists(self.config_path):
            print("Config file not found. Creating with default settings.")
            self.save_config(self.defaults)
            return self.defaults
        
        # Case 2: Config file exists, try to load and verify it
        try:
            with open(self.config_path, 'r') as f:
                config = json.load(f)
            
            # --- Auto-Update: Check for missing keys ---
            missing_keys = False
            for key, value in self.defaults.items():
                if key not in config:
                    print(f"Adding missing config key: {key}")
                    config[key] = value  # Add the default value
                    missing_keys = True
            
            # If we added keys, save the updated config back to the file
            if missing_keys:
                self.save_config(config)
                
            return config
            
        # Case 3: File is corrupt or unreadable
        except Exception as e:
            print(f"Error loading config file: {e}. Loading defaults.")
            return self.defaults  # Fallback to defaults

    def save_config(self, config_data):
        """
        Saves the provided config dictionary to the JSON file.
        
        Args:
            config_data (dict): The configuration dictionary to save.
        """
        try:
            with open(self.config_path, 'w') as f:
                # Use indent=4 for a pretty, human-readable JSON file
                json.dump(config_data, f, indent=4)
            
            # Update the in-memory config to match what was saved
            self.config = config_data
        except Exception as e:
            print(f"Error saving config file: {e}")

    def get(self, key):
        """
        Gets a specific config value by its key.
        
        Falls back to the default value if the key doesn't exist.
        
        Args:
            key (str): The key of the config value to retrieve.
        
        Returns:
            The value associated with the key, or its default.
        """
        # Use .get() for a safe lookup, falling back to the default dict
        return self.config.get(key, self.defaults.get(key))

    def get_all(self):
        """
        Gets the entire config dictionary.
        
        Returns:
            dict: The complete, currently loaded configuration.
        """
        return self.config
    
    def update(self, key, value):
        """
        Updates a single key/value pair in the config and saves the
        entire file.
        
        Args:
            key (str): The key to update.
            value: The new value to set.
        """
        self.config[key] = value
        self.save_config(self.config)