"""core.config
Configuration core: load/save helpers for config.ini.

This module provides a tiny ConfigManager used by the application to read
and persist simple key/value settings. It purposely keeps a small API:
ConfigManager.load(), get(key, fallback), and save().
"""

from configparser import ConfigParser
from pathlib import Path


class ConfigManager:
    """Simple configuration manager backed by an INI file.

    Behaviour:
    - Uses a single DEFAULT section for lookups.
    - Creates the file with sensible defaults if it does not exist.
    """

    def __init__(self, config_path: str = "config/config.ini"):
        self.config_path = Path(config_path)
        self.config = ConfigParser()
        self.load()

    def load(self) -> None:
        """Load configuration from disk, creating defaults when needed."""
        if self.config_path.exists():
            self.config.read(self.config_path)
            return

        # Defaults when there is no config file yet
        self.config["DEFAULT"] = {
            "log_level": "INFO",
            "dry_run": "False",
            "resolution": "1920x1080",
        }
        self.save()

    def get(self, key: str, fallback=None):
        """Return a value from the DEFAULT section or the provided fallback."""
        return self.config["DEFAULT"].get(key, fallback)

    def save(self) -> None:
        """Persist current configuration to disk (creates parent directories)."""
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        with self.config_path.open("w", encoding="utf-8") as fh:
            self.config.write(fh)
