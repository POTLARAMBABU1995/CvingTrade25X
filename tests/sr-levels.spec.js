// Smoke test for SR_LEVELS.html using mocked backend responses
const { test, expect } = require('@playwright/test');
const path = require('path');
const { pathToFileURL } = require('url');

function buildMockPayload(tolerance) {
  return {
    tolerance,
    filters: {},
    rows: [
      {
        sNo: 1,
        symbol: 'ABCDEF',
        price: 245.67,
        priceSort: 245.67,
        tradingDate: '2024-09-01',
        tradingDateSort: '2024-09-01',
        ltcDate: '2024-09-20',
        ltcDateSort: '2024-09-20',
        tradingDays: 15,
        tradingDaysSort: 15,
        score: 72,
        scoreSort: 72,
        touchCounts: { support: 5, resistance: 3 },
        reversalSummary: {
          reversalCount: 4,
          upSwings: 2,
          downSwings: 2,
          pullbacks: 1,
          corrections: 1
        },
        cycleSummary: {
          swingHighDurations: [
            { fromDate: '2024-08-01', toDate: '2024-09-01', tradingDays: 22, months: 1 }
          ],
          swingLowDurations: [
            { fromDate: '2024-07-10', toDate: '2024-08-05', tradingDays: 18, months: 1 }
          ],
          allTimeHighDurations: [
            { fromDate: '2024-06-01', toDate: '2024-09-01', tradingDays: 65, months: 3 }
          ],
          allTimeLowDurations: [],
          fiftyTwoWeekHighDurations: [],
          fiftyTwoWeekLowDurations: [],
          lastUptrendToHigh: { fromDate: '2024-08-10', toDate: '2024-09-01', tradingDays: 15, months: 1 },
          lastDowntrendToLow: null,
          lastConsolidation: null
        },
        momentumSignal: {
          active: true,
          score: 64,
          reasons: ['RSI above 50', 'MACD positive'],
          conditions: {
            macdPositive: true,
            rsiAboveThreshold: true,
            emaStacked: true
          }
        },
        timeframes: {
          daily: {
            supportSummary: 'S1 235.00 (5 touches)',
            resistanceSummary: 'R1 255.00 (3 touches)',
            dominantSupport: { touchesSupport: 5, touchesTotal: 5 },
            dominantResistance: { touchesResistance: 3, touchesTotal: 3 },
            supports: [
              {
                label: 'S1',
                price: 235,
                touchesSupport: 5,
                touchesResistance: 0,
                breaches: 1,
                touchesByTolerance: { ['±5%']: 5 }
              }
            ],
            resistances: [
              {
                label: 'R1',
                price: 255,
                touchesResistance: 3,
                touchesSupport: 0,
                breaches: 0,
                touchesByTolerance: { ['±5%']: 3 }
              }
            ]
          }
        },
        d5: '+2.1%',
        d10: '+3.8%',
        d15: '+5.4%',
        d22: '+6.7%',
        d44: '+8.2%',
        d66: '+12.1%',
        d88: '+15.4%',
        d132: '+19.8%',
        d198: '+25.3%',
        y1: '+30.0%',
        y2: '+42.0%',
        y3: '+55.0%',
        y4: '+65.0%',
        y5: '+72.5%',
        y6: '+80.0%',
        y7: '+90.0%',
        y8: '+95.0%',
        y9: '+100.0%',
        y10: '+110.0%',
        y15: '+180.0%',
        y20: '+220.0%',
        y25: '+260.0%'
      }
    ]
  };
}

test('SR levels loads mocked data and renders details', async ({ page }) => {
  await page.route('**/api/health', (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ db: 'up' })
    });
  });

  await page.route('**/api/sr-levels**', (route) => {
    const requestUrl = new URL(route.request().url());
    const tolerance = Number(requestUrl.searchParams.get('tolerance') || '0.05');
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(buildMockPayload(tolerance))
    });
  });

  const fileUrl = pathToFileURL(path.resolve(__dirname, '../SR_LEVELS.html')).href;
  await page.goto(fileUrl);

  await expect(page.locator('#srStatus')).toContainText('DB Up');

  const rows = page.locator('#srLevelsTable tbody tr');
  await expect(rows).toHaveCount(1);
  await expect(rows.first().locator('td[data-col="symbol"]')).toHaveText('ABCDEF');

  await rows.first().click();
  await expect(page.locator('#srDetails h3')).toHaveText('ABCDEF');
  await expect(page.locator('#srDetails')).toContainText('Momentum checklist', { ignoreCase: true });
});
