// Run with a local static server and Playwright installed.
// PLAYWRIGHT_MODULE=/path/to/playwright node scripts/extension_browser_check.cjs [base URL]
const assert = require('node:assert/strict');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const base = process.argv[2] || 'http://127.0.0.1:5184';
(async () => {
  const browser = await chromium.launch({headless: true});
  try {
    for (const viewport of [{width: 1440, height: 1000}, {width: 390, height: 844}]) {
      const page = await browser.newPage({viewport, reducedMotion: 'reduce'});
      const errors = [], failures = [];
      page.on('pageerror', error => errors.push(error.message));
      page.on('response', response => { if (response.url().startsWith(base) && response.status() >= 400) failures.push(response.url()); });
      await page.goto(`${base}/prorrogacao/`);
      await page.locator('[data-answer="sim"]').waitFor({state: 'visible'});
      await page.waitForFunction(() => !document.querySelector('[data-answer="sim"]').disabled);
      await page.locator('#map canvas').waitFor();
      assert.equal(await page.locator('#map-fallback').isVisible(), false);
      await page.locator('[data-answer="sim"]').click();
      assert.equal(await page.locator('#stat').textContent(), '79,1%');
      assert.match(await page.locator('#feedback').textContent(), /contrário/);
      assert.match(await page.locator('#map-status').textContent(), /104\.108/);
      await page.locator('#next').click();
      assert.equal(await page.locator('#clock').textContent(), '17:49');
      assert.equal(await page.locator('#stat').textContent(), '98,5%');
      assert.match(await page.locator('#map-status').textContent(), /7\.260/);
      await page.locator('#city').selectOption('71072');
      assert.match(await page.locator('#city-result').textContent(), /São Paulo/);
      await page.locator('#next').click();
      assert.equal(await page.locator('#clock').textContent(), '19:06');
      await page.locator('#next').click();
      await page.locator('#records li').first().waitFor();
      assert.equal(await page.locator('#records li').count(), 9);
      assert.match(await page.locator('#records').textContent(), /19:06:21/);
      assert.match(await page.locator('#records').textContent(), /19:10:29/);
      assert.match(await page.locator('#records').textContent(), /21:12/);
      assert.equal(await page.locator('#section-source').getAttribute('href'), '../data/secoes/SP/71072-0001.json');
      await page.locator('#back').click();
      assert.equal(await page.locator('#clock').textContent(), '19:06');
      await page.locator('[data-minute="1020"]').click();
      assert.equal(await page.locator('#clock').textContent(), '17:00');
      await page.locator('#time').focus();
      await page.keyboard.press('ArrowRight');
      assert.equal(await page.locator('#clock').textContent(), '17:01');
      assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), 'horizontal overflow');
      await page.locator('#back').click(); await page.locator('#back').click();
      await page.screenshot({path: `/tmp/brasildb-extension-${viewport.width}.png`, fullPage: true});
      assert.deepEqual(errors, []); assert.deepEqual(failures, []);
      console.log(`${viewport.width}px: narrative, counts, city lookup, evidence, keyboard and overflow pass`);
      await page.close();
    }
    const fallback = await browser.newPage();
    await fallback.route('**/map.js', route => route.abort());
    await fallback.goto(`${base}/prorrogacao/`);
    await fallback.locator('#map-fallback').waitFor({state: 'visible'});
    await fallback.locator('[data-answer="nao"]').click();
    assert.equal(await fallback.locator('#stat').textContent(), '79,1%');
    assert.equal(await fallback.locator('#city').isEnabled(), true);
    console.log('No map module: narrative and city lookup pass');
    await fallback.close();
    const failed = await browser.newPage();
    await failed.route('**/closures.json', route => route.fulfill({status: 503, body: 'Unavailable'}));
    await failed.goto(`${base}/prorrogacao/`);
    await failed.locator('#loading[role="alert"]').waitFor();
    assert(await failed.locator('[data-answer="sim"]').isDisabled());
    console.log('Data failure: visible error and disabled investigation pass');
    await failed.close();
    const noJS = await browser.newPage({javaScriptEnabled: false});
    await noJS.goto(`${base}/prorrogacao/`);
    assert(await noJS.locator('noscript').isVisible());
    assert(await noJS.locator('#fontes').isVisible());
    console.log('No JavaScript: source and method access pass');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
