from src.gangware.gui import build_theme
from src.gangware.gui import design_tokens as T


def test_build_generates_qss(tmp_path):
    # Build to workspace path
    out = build_theme.build()
    assert out.exists(), "theme.qss was not generated"

    qss = out.read_text(encoding="utf-8")

    # Required selectors exist
    required = [
        "#card", "#title", "#divider", "#tab", "#section",
        "#sectionTitle", "#item", "#keycap", "#statusBox", "#status",
    ]
    for sel in required:
        assert sel in qss, f"Missing selector {sel}"

    # Token values appear
    expected_values = [
        T.CYAN, T.ORANGE, T.TEXT_DEFAULT,
        T.STATUS_OK, T.BG_CARD_RGBA, T.BG_SECTION_RGBA,
        T.BORDER_CYAN, T.BORDER_SECTION, T.DIVIDER,
        T.KEYCAP_BG, T.KEYCAP_BORDER, T.STATUSBOX_BG, T.STATUSBOX_BORDER,
        str(T.RADIUS_CARD), str(T.RADIUS_SECTION), str(T.RADIUS_KEYCAP), str(T.RADIUS_TAB),
        str(T.TITLE_SIZE), str(T.SECTION_SIZE),
    ]
    for val in expected_values:
        assert str(val) in qss, f"Token value missing in QSS: {val}"
