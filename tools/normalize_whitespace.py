from pathlib import Path
import sys


def normalize_file(path: Path) -> None:
    text = path.read_text(encoding="utf-8", errors="ignore")
    lines = text.splitlines()
    lines = [ln.rstrip(" \t") for ln in lines]
    while lines and lines[-1] == "":
        lines.pop()
    normalized = "\n".join(lines) + "\n"
    path.write_text(normalized, encoding="utf-8")


if __name__ == "__main__":
    paths = [Path(p) for p in sys.argv[1:]]
    for p in paths:
        if p.suffix == ".py" and p.is_file():
            normalize_file(p)
    print("Normalization complete.")
