"""
Configuration Core Module
Handles configuration loading and saving.
"""

class ConfigManager:
    """
    Loads, gets, and saves settings from config.ini.
    """
    def __init__(self, config_path='config/config.ini'):
        import configparser
        self.config_path = config_path
        self.config = configparser.ConfigParser()
        self.load()

    def load(self):
        """
        Loads configuration from file.
        """
        import os
        if os.path.exists(self.config_path):
            self.config.read(self.config_path)
        else:
            # If config file doesn't exist, create with defaults
            self.config['DEFAULT'] = {
                'log_level': 'INFO',
                'dry_run': 'False',
                'resolution': '1920x1080'
            }
            self.save()

    def get(self, key, fallback=None):
        """
        Gets a configuration value.
        """
        return self.config['DEFAULT'].get(key, fallback)

    def save(self):
        """
        Saves configuration to file.
        """
        with open(self.config_path, 'w') as configfile:
            self.config.write(configfile)
