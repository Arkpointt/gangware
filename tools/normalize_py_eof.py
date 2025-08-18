from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def normalize_file(path: Path) -> None:
    text = path.read_text(encoding="utf-8", errors="ignore")
    # splitlines preserves no trailing empty lines
    lines = text.splitlines()
    # rstrip trailing spaces/tabs on each line
    lines = [ln.rstrip(" \t") for ln in lines]
    # remove trailing empty lines
    while lines and lines[-1] == "":
        lines.pop()
    normalized = "\n".join(lines) + "\n"
    path.write_text(normalized, encoding="utf-8")


if __name__ == "__main__":
    py_files = list(ROOT.rglob("*.py"))
    changed = 0
    for p in py_files:
        # skip virtualenv and hidden folders
        if any(part.startswith(".venv") or part == "venv" or part.startswith(".") for part in p.parts):
            continue
        try:
            normalize_file(p)
            changed += 1
        except Exception as e:
            print(f"skipped {p}: {e}")
    print(f"normalized {changed} .py files")
