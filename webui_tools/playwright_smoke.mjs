import { chromium } from 'playwright';

const BASE = 'https://192.168.1.50:5443';
const USER = 'doktor';
const PASS = '1133';

(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ ignoreHTTPSErrors: true });

  await page.goto(`${BASE}/giris`, { waitUntil: 'domcontentloaded' });
  const usernameInput = await page.$('input[name="username"], input#username, input[type="text"]');
  const passwordInput = await page.$('input[name="password"], input#password, input[type="password"]');

  if (!usernameInput || !passwordInput) {
    throw new Error('Login alanlari bulunamadi. Tarayici sekli degisti veya sayfa acilmadi.');
  }

  await page.fill('input[name="username"], input#username, input[type="text"]', USER);
  await page.fill('input[name="password"], input#password, input[type="password"]', PASS);
  await Promise.all([
    page.waitForNavigation({ waitUntil: 'domcontentloaded' }),
    page.click('button[type="submit"], button:has-text("Giris"), button:has-text("Giriş")')
  ]);

  await page.goto(`${BASE}/hastalar`, { waitUntil: 'domcontentloaded' });
  const hasPatientsPage = (await page.title()).length > 0;

  if (!hasPatientsPage) {
    throw new Error('Hasta listesi acilamadi.');
  }

  await page.screenshot({ path: 'smoke-hastalar.png', fullPage: true });
  await browser.close();
})();
