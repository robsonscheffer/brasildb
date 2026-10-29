// Serve docs/site locally, then run with Playwright available to Node.
// SITE_URL defaults to http://127.0.0.1:8767/v3/. External requests are blocked.
// PLAYWRIGHT_MODULE can point at an existing installation; no production JS dependency.
const assert = require("node:assert/strict");
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || "playwright");
const url = process.env.SITE_URL || "http://127.0.0.1:8767/v3/";
const origin = new URL(url).origin;
let checks = 0;
function ok(name) { console.log(JSON.stringify({ check: name, status: "pass" })); checks++; }

(async () => {
  const browser = await chromium.launch({ headless: true });
  const errors = [];
  async function page(options = {}) {
    const context = await browser.newContext(options);
    await context.route("**/*", route => {
      const target = new URL(route.request().url());
      return target.origin === origin ? route.continue() : route.abort();
    });
    const p = await context.newPage();
    p.on("pageerror", e => errors.push(e.message));
    return p;
  }
  async function ready(p, target = url) {
    await p.goto(target);
    await p.waitForFunction(() => document.body.dataset.ready === "true");
    await p.evaluate(() => document.fonts.ready);
  }
  async function settled(p) { await p.waitForTimeout(400); }
  async function position(p, index) {
    await p.evaluate(i => {
      const r = document.querySelectorAll(".log-record")[i];
      const y = scrollY + r.getBoundingClientRect().top + r.offsetHeight / 2 - innerHeight * .52 + 1;
      scrollTo({ top: y, behavior: "instant" });
    }, index);
    await settled(p);
  }
  try {
    const desktop = await page({ viewport: { width: 1440, height: 1000 }, reducedMotion: "reduce" });
    await ready(desktop);
    assert.equal(await desktop.locator('.log-record[data-type="vote"]').count(), 274);
    const times = await desktop.locator(".log-record").evaluateAll(rows => rows.map(r => r.dataset.time));
    assert.deepEqual(times, [...times].sort());
    assert.equal(times.at(-1), "23:27:02");
    ok("320 chronological records, 274 votes, final publication time");
    assert.equal(times.length, 320);

    for (const width of [320, 390, 600, 768, 900, 1024, 1440, 1920]) {
      await desktop.setViewportSize({ width, height: 900 });
      await settled(desktop);
      const layout = await desktop.evaluate(() => {
        const bar = document.querySelector(".reading-bar-inner").getBoundingClientRect();
        const childrenFit = [...document.querySelector(".reading-bar-inner").children].every(e => {
          const r = e.getBoundingClientRect();
          return !r.width || (r.left >= bar.left - 1 && r.right <= bar.right + 1);
        });
        const labelsFit = [...document.querySelectorAll(".log-label")].every(e =>
          e.getBoundingClientRect().right <= e.parentElement.getBoundingClientRect().right + 1);
        return { overflow: document.documentElement.scrollWidth > innerWidth, childrenFit, labelsFit };
      });
      assert.deepEqual(layout, { overflow: false, childrenFit: true, labelsFit: true }, "width " + width);
    }
    ok("no overflow or clipped tape labels at eight viewport widths, without webfonts");

    await desktop.setViewportSize({ width: 1440, height: 1000 });
    await position(desktop, 100);
    const forward = await desktop.evaluate(() => ({
      active: Number(document.body.dataset.activeEvent),
      time: document.querySelector(".is-current").dataset.time,
      clock: document.getElementById("clock-main").textContent,
      count: Number(document.body.dataset.votes),
      marks: document.querySelectorAll(".vote-marks .read").length,
    }));
    assert.equal(forward.active, 100);
    assert.equal(forward.clock, forward.time.slice(0, 5));
    assert.equal(forward.count, forward.marks);
    await position(desktop, 35);
    assert.equal(await desktop.evaluate(() => Number(document.body.dataset.activeEvent)), 35);
    assert.ok(await desktop.evaluate(() => Number(document.body.dataset.votes)) < forward.count);
    ok("scroll and reverse-scroll keep clock, record and vote marks aligned");

    await desktop.locator('.chapter-nav a[href="#apuracao"]').click();
    await settled(desktop);
    assert.equal(await desktop.getAttribute("body", "data-active-chapter"), "apuracao");
    await position(desktop, 319);
    assert.equal(await desktop.locator("#clock-main").textContent(), "23:27");
    assert.equal(await desktop.locator("#bar-count").textContent(), "274");
    await desktop.waitForTimeout(500);
    assert.equal(await desktop.getAttribute("body", "data-active-event"), "319");
    ok("chapter links work and the ending never loops");

    await ready(desktop, url + "#bateria");
    await settled(desktop);
    assert.equal(await desktop.getAttribute("body", "data-active-chapter"), "bateria");
    await ready(desktop, url + "#%");
    assert.equal(await desktop.getAttribute("body", "data-ready"), "true");
    ok("asynchronous chapter deep link and malformed hash");

    await desktop.goto(url);
    await desktop.waitForFunction(() => document.body.dataset.ready === "true");
    await desktop.keyboard.press("Tab");
    assert.equal(await desktop.evaluate(() => document.activeElement.className), "skip-link");
    await desktop.keyboard.press("Enter");
    await settled(desktop);
    assert.equal(await desktop.evaluate(() => document.activeElement.id), "diario");
    ok("keyboard skip link transfers focus to the diary");

    const mobile = await page({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true, reducedMotion: "reduce" });
    await ready(mobile);
    await mobile.locator(".start-link").click();
    await mobile.locator("#mobile-chapters").selectOption("bateria");
    await settled(mobile);
    assert.equal(await mobile.getAttribute("body", "data-active-chapter"), "bateria");
    assert.equal(await mobile.evaluate(() => document.activeElement.id), "bateria");
    const chapterTop = await mobile.evaluate(() => scrollY);
    await mobile.evaluate(() => scrollBy({ top: 350, behavior: "instant" }));
    await settled(mobile);
    await mobile.locator("#mobile-chapters").selectOption("bateria");
    await settled(mobile);
    assert.ok(Math.abs(await mobile.evaluate(() => scrollY) - chapterTop) < 2);
    ok("the current mobile chapter can be selected again to restart it");
    await mobile.locator("#mobile-chapters").selectOption("apuracao");
    await settled(mobile);
    assert.equal(await mobile.getAttribute("body", "data-active-chapter"), "apuracao");
    assert.ok(await mobile.locator("#mobile-chapters").isVisible());
    ok("mobile sticky chapter selector navigates and moves focus");

    const motion = await mobile.evaluate(() => ({
      scroll: getComputedStyle(document.documentElement).scrollBehavior,
      animations: document.getAnimations().filter(a => a.playState === "running").length,
      parallax: document.getElementById("preview-paper").style.getPropertyValue("--paper-y"),
    }));
    assert.deepEqual(motion, { scroll: "auto", animations: 0, parallax: "" });
    ok("reduced motion disables smooth scroll, animations and parallax");

    await mobile.setViewportSize({ width: 844, height: 390 });
    await mobile.locator("#bateria").evaluate(e => e.scrollIntoView({ behavior: "instant" }));
    await settled(mobile);
    assert.equal(Math.round(await mobile.locator(".reading-bar").evaluate(e => e.getBoundingClientRect().top)), 0);
    assert.ok(await mobile.locator(".site-header").evaluate(e => e.getBoundingClientRect().bottom < 0));
    ok("landscape keeps only the reading bar, not a second fixed header");

    const normal = await page({ viewport: { width: 1440, height: 1000 }, reducedMotion: "no-preference" });
    await ready(normal);
    await normal.waitForTimeout(1300);
    await normal.evaluate(() => scrollTo({ top: 250, behavior: "instant" }));
    await settled(normal);
    assert.notEqual(await normal.locator("#preview-paper").evaluate(e => e.style.getPropertyValue("--paper-y")), "");
    await normal.emulateMedia({ reducedMotion: "reduce" });
    await settled(normal);
    assert.equal(await normal.locator("#preview-paper").evaluate(e => e.style.getPropertyValue("--paper-y")), "");
    assert.equal(await normal.evaluate(() => document.getAnimations().filter(a => a.playState === "running").length), 0);
    ok("motion responds to a runtime preference change, with no idle animation loop");

    function luminance(rgb) {
      const values = rgb.match(/[0-9.]+/g).slice(0, 3).map(Number).map(n => {
        const s = n / 255;
        return s <= .04045 ? s / 12.92 : ((s + .055) / 1.055) ** 2.4;
      });
      return values[0] * .2126 + values[1] * .7152 + values[2] * .0722;
    }
    const contrast = await mobile.evaluate(() => ({
      background: getComputedStyle(document.querySelector(".paper")).backgroundColor,
      text: [".log-record time", ".log-label", ".vote-number small"].map(selector =>
        getComputedStyle(document.querySelector(selector)).color),
    }));
    contrast.text.forEach(color => {
      const a = luminance(color), b = luminance(contrast.background);
      assert.ok((Math.max(a, b) + .05) / (Math.min(a, b) + .05) >= 4.5);
    });
    ok("timestamps, vote labels and small totals meet 4.5:1 text contrast");

    const nojs = await page({ javaScriptEnabled: false });
    await nojs.goto(url);
    assert.ok(await nojs.locator("noscript").isVisible());
    assert.ok(await nojs.locator('noscript a[href="./data/secao.json"]').isVisible());
    assert.equal(await nojs.locator("#loading").isVisible(), false);
    ok("no-JavaScript fallback exposes the source without a permanent spinner");

    const failed = await page();
    await failed.route("**/data/secao.json", route => route.fulfill({ status: 503, body: "" }));
    await failed.goto(url);
    await failed.waitForFunction(() => document.body.dataset.ready === "error");
    assert.ok(await failed.getByRole("alert").isVisible());
    assert.ok(await failed.getByRole("link", { name: "Abrir os registros da seção" }).isVisible());
    ok("unavailable data shows an accessible failure and source link");

    assert.deepEqual(errors, []);
    ok("no uncaught browser errors");
    console.log(JSON.stringify({ checks, status: "pass" }));
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
