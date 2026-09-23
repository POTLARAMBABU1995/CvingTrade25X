from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]


def test_dashboard_ticker_restarts_animation_after_content_updates():
    source = (ROOT / "assets" / "js" / "dashboard.js").read_text(encoding="utf-8")

    assert "function restartTickerAnimation" in source
    assert re.search(
        r"function\s+setTickerContent\s*\([^)]*\)\s*\{[\s\S]*restartTickerAnimation\(el\)",
        source,
    )


def test_dashboard_ticker_runs_by_default_and_pauses_on_cursor_hover_only():
    css = (ROOT / "css" / "styles.css").read_text(encoding="utf-8")

    track_block = re.search(r"\.market-ticker__track\s*\{(?P<body>[^}]*)\}", css)
    assert track_block
    assert "animation-play-state: running" in track_block.group("body")

    hover_block = re.search(r"\.market-ticker:hover\s+\.market-ticker__track\s*\{(?P<body>[^}]*)\}", css)
    assert hover_block
    assert "animation-play-state: paused" in hover_block.group("body")
