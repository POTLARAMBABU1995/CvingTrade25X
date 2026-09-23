import json
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

MOCK_PAYLOAD = {
    "tolerance": 0.05,
    "filters": {},
    "rows": [
        {
            "sNo": 1,
            "symbol": "ABCDEF",
            "price": 245.67,
            "priceSort": 245.67,
            "tradingDate": "2024-09-01",
            "tradingDateSort": "2024-09-01",
            "ltcDate": "2024-09-20",
            "ltcDateSort": "2024-09-20",
            "tradingDays": 15,
            "tradingDaysSort": 15,
            "score": 72,
            "scoreSort": 72,
            "touchCounts": {"support": 5, "resistance": 3},
            "reversalSummary": {
                "reversalCount": 4,
                "upSwings": 2,
                "downSwings": 2,
                "pullbacks": 1,
                "corrections": 1
            },
            "cycleSummary": {
                "swingHighDurations": [
                    {"fromDate": "2024-08-01", "toDate": "2024-09-01", "tradingDays": 22, "months": 1}
                ],
                "swingLowDurations": [
                    {"fromDate": "2024-07-10", "toDate": "2024-08-05", "tradingDays": 18, "months": 1}
                ],
                "allTimeHighDurations": [
                    {"fromDate": "2024-06-01", "toDate": "2024-09-01", "tradingDays": 65, "months": 3}
                ],
                "allTimeLowDurations": [],
                "fiftyTwoWeekHighDurations": [],
                "fiftyTwoWeekLowDurations": [],
                "lastUptrendToHigh": {
                    "fromDate": "2024-08-10",
                    "toDate": "2024-09-01",
                    "tradingDays": 15,
                    "months": 1
                },
                "lastDowntrendToLow": None,
                "lastConsolidation": None
            },
            "momentumSignal": {
                "active": True,
                "score": 64,
                "reasons": ["RSI above 50", "MACD positive"],
                "conditions": {
                    "macdPositive": True,
                    "rsiAboveThreshold": True,
                    "emaStacked": True
                }
            },
            "timeframes": {
                "daily": {
                    "supportSummary": "S1 235.00 (5 touches)",
                    "resistanceSummary": "R1 255.00 (3 touches)",
                    "dominantSupport": {"touchesSupport": 5, "touchesTotal": 5},
                    "dominantResistance": {"touchesResistance": 3, "touchesTotal": 3},
                    "supports": [
                        {
                            "label": "S1",
                            "price": 235,
                            "touchesSupport": 5,
                            "touchesResistance": 0,
                            "breaches": 1,
                            "touchesByTolerance": {"±5%": 5}
                        }
                    ],
                    "resistances": [
                        {
                            "label": "R1",
                            "price": 255,
                            "touchesResistance": 3,
                            "touchesSupport": 0,
                            "breaches": 0,
                            "touchesByTolerance": {"±5%": 3}
                        }
                    ]
                }
            },
            "d5": "+2.1%",
            "d10": "+3.8%",
            "d15": "+5.4%",
            "d22": "+6.7%",
            "d44": "+8.2%",
            "d66": "+12.1%",
            "d88": "+15.4%",
            "d132": "+19.8%",
            "d198": "+25.3%",
            "y1": "+30.0%",
            "y2": "+42.0%",
            "y3": "+55.0%",
            "y4": "+65.0%",
            "y5": "+72.5%",
            "y6": "+80.0%",
            "y7": "+90.0%",
            "y8": "+95.0%",
            "y9": "+100.0%",
            "y10": "+110.0%",
            "y15": "+180.0%",
            "y20": "+220.0%",
            "y25": "+260.0%"
        }
    ]
}

def test_sr_levels_smoke():
    root = Path(__file__).resolve().parents[1]
    file_url = (root / "SR_LEVELS.html").as_uri()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})

        page.route("**/api/health", lambda route: route.fulfill(
            status=200,
            headers={"content-type": "application/json"},
            body=json.dumps({"db": "up"})
        ))

        page.route("**/api/sr-levels**", lambda route: route.fulfill(
            status=200,
            headers={"content-type": "application/json"},
            body=json.dumps(MOCK_PAYLOAD)
        ))

        page.goto(file_url)

        status = page.locator("#srStatus")
        expect(status).to_contain_text("DB Up")

        rows = page.locator("#srLevelsTable tbody tr")
        expect(rows).to_have_count(1)
        expect(rows.first().locator("td[data-col='symbol']")).to_have_text("ABCDEF")

        rows.first().click()
        expect(page.locator("#srDetails h3")).to_have_text("ABCDEF")

        browser.close()
