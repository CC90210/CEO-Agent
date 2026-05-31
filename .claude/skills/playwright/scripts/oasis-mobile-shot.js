// Mobile viewport screenshot (autoplay-driven assembly path).
const { chromium } = require('playwright');

(async () => {
  const url = process.argv[2] || 'http://localhost:3399/welcome';
  const outDir = process.argv[3] || '/tmp/oasis-shots';
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, deviceScaleFactor: 2 });
  const page = await ctx.newPage();
  await page.goto(url, { waitUntil: 'networkidle', timeout: 30000 });

  for (const [name, delayMs] of [['mobile-1s', 1000], ['mobile-4s', 4000], ['mobile-9s', 9000]]) {
    await page.waitForTimeout(delayMs - (name === 'mobile-1s' ? 0 : (name === 'mobile-4s' ? 1000 : 4000)));
    const path = `${outDir}/welcome-${name}.png`;
    await page.screenshot({ path, fullPage: false });
    console.log(JSON.stringify({ name, file: path }));
  }
  await browser.close();
})().catch((e) => { console.error(e); process.exit(1); });
