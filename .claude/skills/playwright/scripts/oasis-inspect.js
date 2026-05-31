// Inspect the actual rendered layout of the figure stage + image at lock state.
const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await ctx.newPage();

  await page.goto('http://localhost:3399/welcome', { waitUntil: 'networkidle', timeout: 30000 });
  await page.waitForTimeout(2000);

  // Scroll to full lock
  const section = await page.evaluate(() => {
    const el = document.getElementById('agent-build');
    const r = el.getBoundingClientRect();
    return { top: r.top + window.scrollY, height: r.height };
  });
  const lockY = Math.round(section.top + 0.995 * (section.height - 900));
  await page.evaluate((y) => window.scrollTo({ top: y, behavior: 'instant' }), lockY);
  await page.waitForTimeout(1500);

  // Find the figure stage and image
  const info = await page.evaluate(() => {
    const stageEl = document.querySelector('[class*="aspect-[540/1435]"]')
      || document.querySelector('[class*="aspect-\\[540"]');
    let stage = null;
    if (stageEl) {
      const r = stageEl.getBoundingClientRect();
      const cs = getComputedStyle(stageEl);
      stage = { x: r.x, y: r.y, w: r.width, h: r.height, overflow: cs.overflow, position: cs.position };
    }
    const imgs = Array.from(document.querySelectorAll('img'))
      .filter(i => i.src.includes('/welcome/parts/'))
      .map(i => {
        const r = i.getBoundingClientRect();
        const cs = getComputedStyle(i);
        return {
          src: i.src.split('/').pop(),
          x: r.x, y: r.y, w: r.width, h: r.height,
          opacity: cs.opacity,
          objectFit: cs.objectFit,
          objectPosition: cs.objectPosition,
        };
      });
    // Also find the sticky parent
    const sticky = document.querySelector('section#agent-build > div');
    let stickyInfo = null;
    if (sticky) {
      const r = sticky.getBoundingClientRect();
      const cs = getComputedStyle(sticky);
      stickyInfo = { y: r.y, h: r.height, overflow: cs.overflow, position: cs.position };
    }
    return { stage, sticky: stickyInfo, imgs, viewport: { w: window.innerWidth, h: window.innerHeight } };
  });
  console.log(JSON.stringify(info, null, 2));

  await browser.close();
})().catch((e) => { console.error(e); process.exit(1); });
