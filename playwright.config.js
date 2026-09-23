// Playwright configuration focused on SR_LEVELS smoke tests
const { devices } = require('@playwright/test');
const path = require('path');

module.exports = {
  testDir: path.join(__dirname, 'tests'),
  timeout: 30 * 1000,
  retries: 0,
  use: {
    headless: true,
    viewport: { width: 1440, height: 900 },
    actionTimeout: 10 * 1000,
    navigationTimeout: 15 * 1000,
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] }
    }
  ]
};
