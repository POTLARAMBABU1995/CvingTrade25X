from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_shared_technical_table_css_is_scoped_and_sticky_safe():
    css = (ROOT / "css" / "styles.css").read_text(encoding="utf-8")

    assert "body.technical-table-enhanced-page main.container" in css
    assert "width: calc(100% - 24px);" in css
    assert "max-width: none;" in css
    assert "--page-sno-width: 72px;" in css
    assert "--page-symbol-width: 140px;" in css
    assert "border-collapse: separate !important;" in css
    assert "border-spacing: 0;" in css
    assert "isolation: isolate;" in css
    assert 'col[data-col="sNo"]' in css
    assert 'col[data-col="symbol"]' in css
    assert "z-index: 60 !important;" in css
    assert "z-index: 59 !important;" in css
    assert "z-index: 40 !important;" in css
    assert "z-index: 39 !important;" in css
    assert ":not(.sticky-sno):not(.sticky-symbol)" in css


def test_shared_technical_table_js_targets_only_matching_pages():
    source = (ROOT / "assets" / "main.js").read_text(encoding="utf-8")

    assert "TECHNICAL_TABLE_ENHANCEMENT_PAGES" in source
    for page in [
        "ema.html",
        "adx.html",
        "macd.html",
        "rsi50.html",
        "atr14.html",
        "volume.html",
        "sr_levels.html",
        "strongtechnicals.html",
        "priceactionanalysis.html",
        "trendline.html",
        "breakout.html",
        "chartpatterns.html",
    ]:
        assert f"'{page}': true" in source

    assert "initTechnicalTableEnhancements();" in source
    assert "ensureTechnicalTableColgroup" in source
    assert "bindTechnicalSymbolCopy" in source
    assert "writeTextToClipboard(symbol)" in source
    assert "Copied: " in source
    assert "technical-index-tone--large" in source
    assert "technical-index-tone--mid" in source
    assert "technical-index-tone--small" in source


def test_strong_technical_generated_table_exposes_column_keys():
    source = (ROOT / "assets" / "js" / "strong-technicals.js").read_text(encoding="utf-8")

    assert 'th data-col="${escapeHtml(key)}"' in source
    assert 'data-sort-key="${escapeHtml(key)}"' in source
    assert 'td data-col="${escapeHtml(key)}"' in source
    assert 'technicalTableHead' in source
    assert 'technicalTableBody' in source
