// Presentation-only journey with a fresh browser context and local fixtures.
// Run with Node and NODE_PATH pointing to an existing Playwright installation.
const {chromium} = require('playwright');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const {timeHeaders, timeData} = require('./timezone_fixture.cjs');

const decision = {
  status: 'available', decision_id: 'weather-copy-fixture', catalog_key: 'M31',
  target: 'Galaxie d’Andromède', target_decision_status: 'recommended', action: 'observe',
  night_date: '2026-11-21', window_start: '2026-11-21T20:00:00+01:00',
  window_end: '2026-11-21T22:00:00+01:00', recommended_hours: 1.5,
  selected_filter: {name: 'L-Pro', filter_type: 'broadband'},
  astro_quality: {score: 78, decision_score: 78, decision_eligible: true, label: 'good'},
  recommendation_confidence: .84,
  weather_trust: {provider: 'fixture-provider', validation_status: 'validated',
    freshness_status: 'fresh', timezone: 'Europe/Zurich', snapshot_age_minutes: 15,
    maximum_age_minutes: 120, retrieved_at_utc: '2026-11-21T10:00:00Z',
    valid_from: '2026-11-21T18:00:00Z', valid_until: '2026-11-22T06:00:00Z'},
  weather_decision: {admissibility: 'admissible', presentation: {label: 'Prévisions disponibles',
    summary: 'Conditions du jeu de test'}},
};

(async () => {
  const browser = await chromium.launch({headless: true, channel: 'chrome'});
  try {
    const page = await browser.newPage({timezoneId: 'Europe/Zurich'});
    const web = path.resolve(__dirname, '../../astropilot/web');
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.route('**/*', route => {
      const url = new URL(route.request().url());
      if (url.origin !== 'https://nightmerit.test') return route.abort();
      if (url.pathname === '/ui/timezone-data.js') {
        return route.fulfill({headers: timeHeaders, contentType: 'text/javascript', body: timeData});
      }
      const name = url.pathname === '/' ? 'index.html' : url.pathname.slice('/ui/'.length);
      if ((url.pathname === '/' || url.pathname.startsWith('/ui/'))
          && path.basename(name) === name && fs.existsSync(path.join(web, name))) {
        const contentType = name.endsWith('.js') ? 'text/javascript'
          : name.endsWith('.css') ? 'text/css' : name.endsWith('.html') ? 'text/html' : 'image/jpeg';
        return route.fulfill({headers: timeHeaders, contentType, body: fs.readFileSync(path.join(web, name))});
      }
      return route.fulfill({headers: timeHeaders, status: 503, contentType: 'application/json', body: '{}'});
    });
    await page.goto('https://nightmerit.test/');
    await page.waitForFunction(() => appliedUiMode !== null);

    for (const mode of ['simple', 'pro']) for (const width of [390, 1280]) {
      await page.setViewportSize({width, height: 800});
      await page.evaluate(({mode, decision}) => {
        state.configuration = {configured: true, site: {latitude: 46.9, longitude: 6.9, timezone: 'Europe/Zurich'}};
        applyUiMode(mode);
        renderDecision(decision);
      }, {mode, decision});
      const block = page.locator('#local-weather-explanation');
      const disclosure = block.locator('details');
      const summary = block.locator('summary');
      assert.equal(await block.isVisible(), true);
      assert.match(await block.locator(':scope > p').innerText(), /La température et l’humidité prévues peuvent différer des conditions sur votre site\./);
      assert.equal(await disclosure.evaluate(el => el.open), false);
      assert.equal(await block.locator('input,button,a').count(), 0);
      assert.doesNotMatch(await block.innerText(), /98\s*%|±|SIO|SAE|calibration|B01/);
      const before = await page.evaluate(() => ({
        state: JSON.stringify(state),
        score: document.querySelector('#quality-score').textContent,
        target: document.querySelector('#target-name').textContent,
        window: document.querySelector('#window-value').textContent,
        duration: document.querySelector('#duration-value').textContent,
        actionDisabled: document.querySelector('#open-mission').disabled,
      }));
      assert.equal(before.score, '78');
      assert.equal(before.actionDisabled, false);
      const writes = [];
      const onRequest = request => { if (request.method() !== 'GET') writes.push(request.url()); };
      page.on('request', onRequest);
      await summary.focus();
      assert.equal(await summary.evaluate(el => el === document.activeElement), true);
      await page.keyboard.press('Space');
      assert.equal(await disclosure.evaluate(el => el.open), true);
      assert.equal(await disclosure.locator('p').isVisible(), true);
      assert.match(await disclosure.locator('p').innerText(), /Consultez les observations locales récentes lorsqu’elles sont disponibles/);
      assert.match(await disclosure.locator('p').innerText(), /ne suffisent pas, à elles seules, à garantir la qualité du ciel/);
      const bounds = await block.evaluate(el => {
        const rect = el.getBoundingClientRect();
        return {left: rect.left, right: rect.right, overflow: el.scrollWidth > el.clientWidth};
      });
      assert.ok(bounds.left >= 0 && bounds.right <= width, JSON.stringify({mode, width, bounds}));
      assert.equal(bounds.overflow, false);
      if (process.env.WEATHER_COPY_ARTIFACT_DIR) {
        fs.mkdirSync(process.env.WEATHER_COPY_ARTIFACT_DIR, {recursive: true});
        await block.screenshot({path: path.join(process.env.WEATHER_COPY_ARTIFACT_DIR, `${mode}-${width}.png`)});
      }
      await page.keyboard.press('Enter');
      assert.equal(await disclosure.evaluate(el => el.open), false);
      const after = await page.evaluate(() => ({
        state: JSON.stringify(state),
        score: document.querySelector('#quality-score').textContent,
        target: document.querySelector('#target-name').textContent,
        window: document.querySelector('#window-value').textContent,
        duration: document.querySelector('#duration-value').textContent,
        actionDisabled: document.querySelector('#open-mission').disabled,
      }));
      assert.deepEqual(after, before);
      assert.deepEqual(writes, []);
      page.off('request', onRequest);
    }
    // Information remains generic when weather evidence is missing or stale.
    for (const trust of [null, {...decision.weather_trust, freshness_status: 'stale'}]) {
      await page.evaluate(trust => renderWeatherTrust(trust, null, 'classic'), trust);
      assert.equal(await page.locator('#local-weather-explanation').isVisible(), true);
      assert.equal(await page.locator('#classic-weather-status').textContent(), 'Non disponible');
    }
    assert.deepEqual(errors, []);
    console.log('PASS: local weather explanation, Simple/Pro, mobile/desktop, keyboard, unchanged state and scores');
  } finally {
    await browser.close();
  }
})().catch(error => {console.error(error); process.exitCode = 1;});
