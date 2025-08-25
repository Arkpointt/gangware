from __future__ import annotations

import sys
from pathlib import Path

root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root / "src"))

from gangware.core.config import ConfigManager  # noqa: E402


def main() -> None:
    cfg = ConfigManager()

    menus = [
        ("anchors_main_menu", "Main_Menu"),
        ("anchors_select_game", "Select_Game"),
        ("anchors_server_browser", "Server_Browser"),
    ]

    changed = 0
    for list_key, prefix in menus:
        names_csv = cfg.get(list_key, "") or ""
        names = [n.strip() for n in names_csv.split(",") if n.strip()]
        for name in names:
            base = f"anchor_{name}_thresh"
            cfg.config["DEFAULT"][base] = "0.70"
            changed += 1
    cfg.save()
    print(f"Updated {changed} anchor thresholds to 0.70 in {cfg.config_path}")


if __name__ == "__main__":
    main()
