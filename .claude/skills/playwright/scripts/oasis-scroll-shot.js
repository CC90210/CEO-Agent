// Scroll the OASIS welcome page through the scroll-driven assembly and capture
// screenshots at meaningful phase boundaries. The agent-build section is
// min-h-[780vh] on lg, sticky inside. Compaction fires at section progress
// 0.909–0.989. We must scroll into the SECTION's active range, not the
// whole document, otherwise we screenshot the post-unstick layout.
const { chromium } = require('playwright');

(async () => {
  const url = process.argv[2] || 'http://localhost:3399/welcome';
  const outDir = process.argv[3] || '/tmp/oasis-shots';

  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await ctx.newPage();

  await page.goto(url, { waitUntil: 'networkidle', timeout: 30000 });
  await page.waitForTimeout(2000);

  const section = await page.evaluate(() => {
    const el = document.getElementById('agent-build');
    if (!el) return null;
    const r = el.getBoundingClientRect();
    return {
      top: r.top + window.scrollY,
      height: r.height,
      viewportH: window.innerHeight,
    };
  });
  if (!section) { console.error('agent-build section not found'); process.exit(2); }
  const startY = section.top;
  const endY = section.top + section.height - section.viewportH;
  const range = endY - startY;
  console.log(JSON.stringify({ sectionTop: section.top, sectionHeight: section.height, startY, endY, range }));

  const checkpoints = [
    { name: '00-start',         progress: 0.00 },
    { name: '02-early',         progress: 0.18 },
    { name: '05-mid',           progress: 0.45 },
    { name: '08-late',          progress: 0.73 },
    { name: '10-pre-compact',   progress: 0.89 },
    { name: '11a-compact-25',   progress: 0.93 },
    { name: '11b-compact-60',   progress: 0.957 },
    { name: '11c-compact-end',  progress: 0.985 },
    { name: '12-fully-locked',  progress: 0.995 },
  ];

  for (const cp of checkpoints) {
    const y = Math.round(startY + cp.progress * range);
    await page.evaluate((sy) => window.scrollTo({ top: sy, behavior: 'instant' }), y);
    await page.waitForTimeout(1100);
    const path = `${outDir}/welcome-${cp.name}.png`;
    await page.screenshot({ path, fullPage: false });
    console.log(JSON.stringify({ name: cp.name, progress: cp.progress, scrollY: y, file: path }));
  }

  await browser.close();
})().catch((e) => { console.error(e); process.exit(1); });
