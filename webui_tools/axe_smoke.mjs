import { chromium } from 'playwright';
import AxeBuilder from '@axe-core/playwright';

const baseUrl = process.env.YK_BASE_URL || 'https://127.0.0.1:5443';
const targets = [
  '/giris',
  '/status'
];

const browser = await chromium.launch({
  headless: true,
  args: ['--ignore-certificate-errors']
});

let failures = 0;

try {
  const context = await browser.newContext({ ignoreHTTPSErrors: true });
  const page = await context.newPage();

  for (const path of targets) {
    const url = `${baseUrl}${path}`;
    await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 30000 });
    const results = await new AxeBuilder({ page }).analyze();
    const serious = results.violations.filter((v) =>
      ['critical', 'serious'].includes(v.impact || '')
    );
    console.log(`[axe] ${path}: ${results.violations.length} violation, ${serious.length} serious/critical`);
    if (serious.length) {
      failures += serious.length;
      for (const item of serious.slice(0, 5)) {
        console.log(`  - ${item.impact}: ${item.id} (${item.nodes.length} node)`);
      }
    }
  }
} finally {
  await browser.close();
}

if (failures > 0 && process.env.AXE_STRICT === '1') {
  process.exitCode = 1;
} else if (failures > 0) {
  console.log(`[axe] ${failures} serious/critical bulgu raporlandi; AXE_STRICT=1 verilmedigi icin smoke testi gecirildi.`);
}
