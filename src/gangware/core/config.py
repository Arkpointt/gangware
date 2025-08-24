"""core.config
Configuration core: load/save helpers for config.ini.

This module provides a tiny ConfigManager used by the application to read
and persist simple key/value settings. It purposely keeps a small API:
ConfigManager.load(), get(key, fallback), and save().
"""

import os
from configparser import ConfigParser
from pathlib import Path
from typing import Optional


class ConfigManager:
    """Simple configuration manager backed by an INI file.

    Behaviour:
    - Uses a single DEFAULT section for lookups.
    - Creates the file with sensible defaults if it does not exist.
    - Defaults to a per-user config path (%APPDATA% on Windows,
      XDG_CONFIG_HOME or ~/.config on other systems) unless an explicit
      path is provided.
    """

    def __init__(self, config_path: Optional[str] = None) -> None:
        if config_path:
            self.config_path = Path(config_path)
        else:
            if os.name == "nt":
                base = Path(os.getenv("APPDATA", Path.home() / "AppData" / "Roaming"))
            else:
                base = Path(os.getenv("XDG_CONFIG_HOME", Path.home() / ".config"))
            self.config_path = base.joinpath("Gangware", "config.ini")

        self.config = ConfigParser()
        self.load()

    def load(self) -> None:
        """Load configuration from disk, creating defaults when needed."""
        if self.config_path.exists():
            self.config.read(self.config_path)

        # Ensure DEFAULT section exists (for resolution monitoring and other defaults)
        if "DEFAULT" not in self.config:
            self.config["DEFAULT"] = {}

        # Set default values if they don't exist
        defaults = {
            "log_level": "INFO",
            "dry_run": "False",
            "resolution": "1920x1080",
            "ui_theme": "dark",
            "calibration_complete": "False",
            "inventory_key": "",
            "tek_punch_cancel_key": "",
            # Basic tek punch timing (tek punch works with these simple settings)
            "tek_punch_pre_rmb_delay_ms": "120",
            "tek_punch_rmb_hold_ms": "800",  # Working value from logs
            "tek_punch_post_rmb_settle_ms": "180",
            "search_bar_template": "",
            "ui_demo": "False",
        }

        for key, value in defaults.items():
            if key not in self.config["DEFAULT"]:
                self.config["DEFAULT"][key] = value

        # Save if we added any defaults to existing config
        if self.config_path.exists() and any(key not in self.config["DEFAULT"] for key in defaults):
            self.save()

    def get(self, key: str, fallback=None):
        """Get a configuration value with precedence: env > config.ini > fallback.

        Env precedence checks the following keys in order and returns the first
        non-empty result:
        - GW_<KEY_UPPER>
        - <KEY_UPPER>
        - <key> (exact name)
        """
        try:
            # Environment precedence (allows runtime overrides without editing files)
            env_candidates = [f"GW_{str(key).upper()}", str(key).upper(), str(key)]
            for ek in env_candidates:
                val = os.environ.get(ek)
                if val is not None and str(val) != "":
                    return val
        except Exception:
            # Fall back silently to config.ini lookup
            pass
        return self.config["DEFAULT"].get(key, fallback)

    def save(self) -> None:
        """Persist current configuration to disk (creates parent directories)."""
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        with self.config_path.open("w", encoding="utf-8") as fh:
            self.config.write(fh)
