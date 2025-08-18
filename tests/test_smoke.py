"""Minimal smoke tests to ensure modules import and core managers work."""

from src.gangware.core.config import ConfigManager
from src.gangware.core.state import StateManager


def test_config_defaults_and_save(tmp_path, monkeypatch):
    # Use a temp config path
    cfg_path = tmp_path / "config.ini"
    cfg = ConfigManager(str(cfg_path))
    # Defaults present
    assert cfg.get("log_level") == "INFO"
    assert cfg.get("resolution") == "1920x1080"
    assert cfg.get("ui_theme") == "dark"
    # Modify and save
    cfg.config["DEFAULT"]["log_level"] = "DEBUG"
    cfg.save()
    # Reload and verify persistence
    cfg2 = ConfigManager(str(cfg_path))
    assert cfg2.get("log_level") == "DEBUG"


def test_state_manager_basic_ops():
    st = StateManager()
    assert st.get("missing") is None
    st.set("a", 1)
    assert st.get("a") == 1
    st.remove("a")
    assert st.get("a") is None
    st.set("b", 2)
    st.clear()
    assert st.get("b") is None
