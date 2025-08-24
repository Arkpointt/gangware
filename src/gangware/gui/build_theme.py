"""
Builds theme.qss from theme.qss.j2 and design_tokens.py without external deps.
Usage:
    python -m src.gangware.gui.build_theme
"""
from __future__ import annotations
import re
from pathlib import Path

# Import tokens directly
from . import design_tokens as T

HERE = Path(__file__).parent
TEMPLATE = HERE / "theme.qss.j2"
OUTPUT = HERE / "theme.qss"

# Very small Jinja-like replacement (no external deps)
TOKEN_PATTERN = re.compile(r"{{\s*([A-Z_]+)\s*}}")


def render_template(template_text: str, context: dict[str, str]) -> str:
    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in context:
            raise KeyError(f"Missing token '{key}' in context")
        return str(context[key])

    return TOKEN_PATTERN.sub(replace, template_text)


def build() -> Path:
    with TEMPLATE.open("r", encoding="utf-8") as f:
        tpl = f.read()

    context = {k: getattr(T, k) for k in dir(T) if k.isupper()}
    out = render_template(tpl, context)

    OUTPUT.write_text(out, encoding="utf-8")
    return OUTPUT


def main() -> None:
    out_path = build()
    print(f"Generated: {out_path}")


if __name__ == "__main__":
    main()
