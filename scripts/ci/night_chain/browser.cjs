'use strict';
// Real DOM + HTTP integration. Observe responses; never replace backend results.
const fs = require('node:fs');
const path = require('node:path');
const cp = require('node:child_process');
const assert = require('node:assert/strict');
const {browserEnvironment} = require('./browser_environment.cjs');
assert(typeof WebSocket === 'function', 'Node with built-in WebSocket is required');
const root = process.env.CASE_ROOT, proof = process.env.CASE_PROOF;
const intent = process.env.UI_INTENT, url = process.env.NIGHT_CHAIN_URL;
assert(['sh2-129_ha', 'ou4_oiii', 'site_changed'].includes(intent));
assert(new URL(url).hostname === '127.0.0.1');
const chrome = process.env.CHROME_BINARY;
assert(chrome && fs.existsSync(chrome), 'Pinned testing browser is required');
const profile = path.join(root, 'browser-profile');
fs.mkdirSync(profile);
const log = fs.openSync(path.join(proof, 'browser.log'), 'w');
const env = browserEnvironment(process.env);
const child = cp.spawn(chrome, [
  '--headless=new', '--disable-gpu', '--no-first-run', '--no-default-browser-check',
  '--disable-background-networking', '--remote-debugging-port=0',
  `--user-data-dir=${profile}`, 'about:blank',
], {stdio: ['ignore', log, log], env});
let spawnError;
child.on('error', error => { spawnError = error; });
fs.writeFileSync(path.join(proof, 'browser-environment.json'), JSON.stringify({
  mac_ci_native_home: process.platform === 'darwin' && process.env.GITHUB_ACTIONS === 'true',
  application_home: process.env.HOME, browser_home: env.HOME,
  browser_profile: profile, application_data: process.env.ASTROPILOT_DATA_DIR,
}));
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
let ws, serial = 0;
const pending = new Map();
async function stopBrowser() {
  if (child.exitCode === null && child.signalCode === null && child.pid) {
    if (process.platform === 'win32') {
      cp.spawnSync('taskkill', ['/PID', String(child.pid), '/T', '/F'], {timeout: 10000});
    } else {
      child.kill('SIGTERM');
      for (let n = 0; n < 30 && child.exitCode === null && child.signalCode === null; n++) await pause(100);
      if (child.exitCode === null && child.signalCode === null) child.kill('SIGKILL');
    }
    for (let n = 0; n < 50 && child.exitCode === null && child.signalCode === null; n++) await pause(100);
    assert(child.exitCode !== null || child.signalCode !== null, 'Browser did not stop');
  }
}
const deadline = setTimeout(() => {
  console.error('Browser journey global deadline');
  stopBrowser().finally(() => process.exit(1));
}, 150000);
async function waitFor(fn, label, ms = 45000) {
  const end = Date.now() + ms;
  while (Date.now() < end) {
    if (spawnError) throw spawnError;
    const value = await fn();
    if (value) return value;
    await pause(150);
  }
  throw Error(`Timeout: ${label}`);
}
async function send(method, params = {}) {
  const id = ++serial;
  console.log('CDP', method);
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => { pending.delete(id); reject(Error(`CDP timeout: ${method}`)); }, 15000);
    pending.set(id, {resolve, reject, timer});
    ws.send(JSON.stringify({id, method, params}));
  });
}
async function evaluate(expression) {
  const result = await send('Runtime.evaluate', {expression, awaitPromise: true, returnByValue: true});
  if (result.exceptionDetails) throw Error(JSON.stringify(result.exceptionDetails));
  return result.result.value;
}
async function journey() {
  await waitFor(() => fs.existsSync(path.join(profile, 'DevToolsActivePort')), 'browser debugger');
  const port = fs.readFileSync(path.join(profile, 'DevToolsActivePort'), 'utf8').split('\n')[0];
  const target = await (await fetch(`http://127.0.0.1:${port}/json/new?about:blank`, {
    method: 'PUT', signal: AbortSignal.timeout(10000),
  })).json();
  ws = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(Error('WebSocket open timeout')), 10000);
    ws.onopen = () => { clearTimeout(timer); resolve(); };
    ws.onerror = reject;
  });
  ws.onmessage = event => {
    const message = JSON.parse(event.data);
    if (message.id && pending.has(message.id)) {
      const entry = pending.get(message.id);
      pending.delete(message.id);
      clearTimeout(entry.timer);
      message.error ? entry.reject(Error(JSON.stringify(message.error))) : entry.resolve(message.result);
    }
  };
  await send('Page.enable');
  await send('Runtime.enable');
  await send('Emulation.setDeviceMetricsOverride', {width: 1280, height: 1200, deviceScaleFactor: 1, mobile: false});
  await send('Emulation.setTimezoneOverride', {timezoneId: 'Europe/Zurich'});
  await send('Page.addScriptToEvaluateOnNewDocument', {source: `
    const RealDate = Date;
    window.Date = class extends RealDate {
      constructor(...args) { super(...(args.length ? args : ['2026-10-14T12:00:00Z'])); }
      static now() { return RealDate.parse('2026-10-14T12:00:00Z'); }
    };
    window.__ciTraffic = [];
    const realFetch = window.fetch.bind(window);
    window.fetch = async (...args) => {
      const response = await realFetch(...args);
      if (['POST', 'PUT'].includes(args[1]?.method)) {
        const body = await response.clone().json().catch(() => null);
        window.__ciTraffic.push({url: String(args[0]), request: JSON.parse(args[1].body || 'null'), http: response.status, body});
      }
      return response;
    };
  `});
  await send('Page.navigate', {url});
  await waitFor(() => evaluate(`Boolean(document.querySelector('#availability-step') && !document.querySelector('#availability-step').hidden)`), 'availability UI');
  await evaluate(`
    document.querySelector('input[name="availability-mode"][value="fixed_window"]').click();
    document.querySelector('#availability-start').value = '2026-10-16T00:30';
    document.querySelector('#availability-end').value = '2026-10-16T03:30';
    document.querySelector('#request-recommendation').click(); true;
  `);
  const prepared = await waitFor(() => evaluate(`window.__ciTraffic.find(x => x.url === '/v1/tonight')`), 'Tonight response');
  assert.equal(prepared.http, 200);
  assert.equal(prepared.body.night_date, '2026-10-15');
  assert.deepEqual([...prepared.body.viable_acquisition_intent_ids].sort(), ['ou4_oiii', 'sh2-129_ha']);
  const nightText = await evaluate(`document.querySelector('#night-date').textContent`);
  assert.equal(nightText, 'jeudi 15 octobre');
  let record;
  if (intent === 'site_changed') {
    await evaluate(`
      document.querySelector('#edit-configuration').click();
      document.querySelector('#site-latitude').value = '46.9';
      document.querySelector('#site-next').click();
      document.querySelector('#equipment-next').click();
      document.querySelector('#save-configuration').click(); true;
    `);
    const changed = await waitFor(() => evaluate(`window.__ciTraffic.find(x => x.url === '/v1/configuration')`), 'configuration save');
    assert.equal(changed.http, 200);
    assert.equal(changed.request.site.latitude, 46.9);
    assert.equal(changed.body.site.latitude, 46.9);
    await waitFor(() => evaluate(`Boolean(!document.querySelector('#availability-step').hidden)`), 'availability after site edit');
    assert.equal(await evaluate(`window.__ciTraffic.filter(x => x.url === '/v1/decision-selections').length`), 0);
    assert.equal(await evaluate('state.currentDecision === null'), true);
    record = {prepared, changed, old_decision_cleared: true, no_confirmation_sent: true};
  } else {
    await waitFor(() => evaluate(`Boolean(document.querySelector('#primary-intent-choice select'))`), 'intent selector');
    await evaluate(`
      const select = document.querySelector('#primary-intent-choice select');
      select.value = ${JSON.stringify(intent)};
      select.dispatchEvent(new Event('change', {bubbles: true}));
      document.querySelector('#open-mission').click(); true;
    `);
    const accepted = await waitFor(() => evaluate(`window.__ciTraffic.find(x => x.url === '/v1/decision-selections')`), 'confirmation');
    assert.equal(accepted.http, 200);
    assert.equal(accepted.body.status, 'accepted');
    assert.equal(accepted.body.selected_acquisition_intent_id, intent);
    const filter = accepted.body.mission.selected_filter;
    assert.equal(filter.source, 'authorized_optical_profile');
    assert.equal(filter.filter_type, intent === 'ou4_oiii' ? 'OIII' : 'Ha');
    assert.equal(filter.bandwidth_nm, 6.5);
    const start = Date.parse(accepted.body.mission.window_start), end = Date.parse(accepted.body.mission.window_end);
    assert(start >= Date.parse('2026-10-16T00:30:00+02:00') && start < end && end <= Date.parse('2026-10-16T03:30:00+02:00'));
    await waitFor(() => evaluate(`Boolean(document.querySelector('#mission-filter')?.textContent.includes(${JSON.stringify(filter.filter_type)}))`), 'rendered optical filter');
    const taskRows = await evaluate(`Array.from(document.querySelectorAll('#mission-tasks li'), row => row.textContent)`);
    assert.equal(taskRows.length, 4);
    assert(taskRows.every(row => !/T-\d|Fin \+/.test(row)));
    const formatTaskInstant = instant => new Intl.DateTimeFormat('fr-CH', {
      timeZone: accepted.body.mission.site_timezone, year:'numeric',month:'2-digit',day:'2-digit',
      hour:'2-digit',minute:'2-digit',hour12:false,timeZoneName:'shortOffset',
    }).format(new Date(instant));
    assert(taskRows[0].includes(formatTaskInstant(start - 30 * 60000)));
    assert(taskRows[1].includes(formatTaskInstant(start - 20 * 60000)));
    assert(taskRows[2].includes('Régler la mise au point automatique'));
    assert(taskRows[3].includes(formatTaskInstant(end + 10 * 60000)));
    assert(taskRows[3].includes('Prendre les images de calibration (flats)'));
    const replay = await evaluate(`(async () => {
      const response = await fetch('/v1/decision-selections', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(${JSON.stringify(accepted.request)})});
      return {http: response.status, body: await response.json()};
    })()`);
    assert.equal(replay.http, 200);
    assert.equal(replay.body.mission_id, accepted.body.mission_id);
    await send('Emulation.setDeviceMetricsOverride', {width:390,height:844,deviceScaleFactor:1,mobile:false});
    const planFits = await evaluate(`(() => {
      const list = document.querySelector('#mission-tasks');
      const box = list.getBoundingClientRect();
      return box.width > 0 && box.left >= 0 && box.right <= window.innerWidth &&
        list.scrollWidth <= list.clientWidth + 1;
    })()`);
    assert(planFits, 'Mission plan must remain readable without horizontal overflow at 390px');
    const mobileShot = await send('Page.captureScreenshot', {format:'png',captureBeyondViewport:true});
    fs.writeFileSync(path.join(proof,'mission-mobile.png'),Buffer.from(mobileShot.data,'base64'));
    record = {prepared, accepted, task_rows: taskRows, local_mission_times: true,
      mission_plan_fits_390px: planFits, idempotent_confirmation: true};
  }
  const screenshot = await send('Page.captureScreenshot', {format: 'png', captureBeyondViewport: true});
  fs.writeFileSync(path.join(proof, 'ui.png'), Buffer.from(screenshot.data, 'base64'));
  fs.writeFileSync(path.join(proof, 'ui.txt'), await evaluate('document.body.innerText'));
  fs.writeFileSync(path.join(proof, 'browser-result.json'), JSON.stringify({
    ...record, result: 'PASS', intent, requested_night_text: nightText,
    real_dom_interaction: true, backend_response_replaced: false,
    clock_fixture: '2026-10-14T12:00:00Z', timezone: 'Europe/Zurich',
  }, null, 2));
}
(async () => {
  try { await journey(); }
  finally {
    clearTimeout(deadline);
    for (const entry of pending.values()) clearTimeout(entry.timer);
    if (ws) ws.close();
    await stopBrowser();
    fs.closeSync(log);
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
