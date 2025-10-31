import json
import os

class ConfigManager:
    def __init__(self, config_file='config.json'):
        # Path fix: Go up one level (to 'project') for the config file
        script_dir = os.path.dirname(os.path.abspath(__file__))
        self.config_path = os.path.normpath(os.path.join(script_dir, "..", config_file))
        
        # Default settings
        self.defaults = {
            'ARDUINO_PORT': "COM5",
            'INTENT_TIME_SEC': 1.0,       
            'LOITER_TIME_SEC': 10.0,      
            'COUNTDOWN_SECONDS': 10,      
            'CONFIDENCE_THRESH': 86,
            'ADMIN_PASSWORD': "admin"
        }
        
        self.config = self.load_config()

    def load_config(self):
        """Loads config from file, or creates file with defaults if it doesn't exist."""
        if not os.path.exists(self.config_path):
            print("Config file not found. Creating with default settings.")
            self.save_config(self.defaults)
            return self.defaults
        
        try:
            with open(self.config_path, 'r') as f:
                config = json.load(f)
                # Check for missing keys and add them
                for key, value in self.defaults.items():
                    if key not in config:
                        config[key] = value
                self.save_config(config) # Save back to add new keys
                return config
        except Exception as e:
            print(f"Error loading config file: {e}. Loading defaults.")
            return self.defaults

    def save_config(self, config_data):
        """Saves the config dictionary to the JSON file."""
        try:
            with open(self.config_path, 'w') as f:
                json.dump(config_data, f, indent=4)
            self.config = config_data # Update the internal config
        except Exception as e:
            print(f"Error saving config file: {e}")

    def get(self, key):
        """Gets a specific config value."""
        return self.config.get(key, self.defaults.get(key))

    def get_all(self):
        """Gets the entire config dictionary."""
        return self.config
    
    def update(self, key, value):
        """Updates a single key in the config and saves."""
        self.config[key] = value
        self.save_config(self.config)