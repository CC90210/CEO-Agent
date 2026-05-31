// Smoke-test the live oasis-command-center Vercel deploy after the
// fix/chat-and-auth-turnkey ship. Hits the two public pages that the
// changes touched (/welcome — AuthRedirectGuard inject, /login —
// AuthRedirectGuard + email-pass form), checks for JS errors, takes a
// desktop + mobile screenshot of each, and reports.
//
// We can't reach the authed /agents surface without credentials, so
// the chat/sidebar/history visual fixes are verified by:
//   (a) build success (compile-time JSX validity),
//   (b) Codex independent audit on the diff,
//   (c) operator visual confirmation post-deploy.
const { chromium } = require('playwright');

const BASE = process.argv[2] || 'https://agent-dashboard-cc90210.vercel.app';
const OUT = process.argv[3] || '/tmp/oasis-smoke';

async function smoke(page, path, label) {
  const url = `${BASE}${path}`;
  const errs = [];
  page.on('pageerror', (e) => errs.push(`pageerror: ${e.message}`));
  page.on('console', (msg) => {
    if (msg.type() === 'error') errs.push(`console: ${msg.text().slice(0, 200)}`);
  });
  let status = 0;
  try {
    const resp = await page.goto(url, { waitUntil: 'networkidle', timeout: 30000 });
    status = resp?.status() || 0;
  } catch (e) {
    return { path, label, status, ok: false, errs: [`goto: ${e.message}`] };
  }
  await page.waitForTimeout(500);
  const shot = `${OUT}/${label}.png`;
  await page.screenshot({ path: shot, fullPage: false });
  return { path, label, status, ok: status === 200 && errs.length === 0, errs, shot };
}

(async () => {
  const browser = await chromium.launch();
  const results = [];

  // Desktop
  const desktop = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  for (const [path, label] of [['/welcome', 'welcome-desktop'], ['/login', 'login-desktop']]) {
    const p = await desktop.newPage();
    results.push(await smoke(p, path, label));
    await p.close();
  }
  await desktop.close();

  // Mobile (iPhone 13 width)
  const mobile = await browser.newContext({
    viewport: { width: 390, height: 844 },
    isMobile: true,
    deviceScaleFactor: 2,
  });
  for (const [path, label] of [['/welcome', 'welcome-mobile'], ['/login', 'login-mobile']]) {
    const p = await mobile.newPage();
    results.push(await smoke(p, path, label));
    await p.close();
  }
  await mobile.close();

  await browser.close();
  console.log(JSON.stringify({ base: BASE, results }, null, 2));
  const failed = results.filter((r) => !r.ok);
  process.exit(failed.length === 0 ? 0 : 1);
})().catch((e) => {
  console.error(e);
  process.exit(2);
});
