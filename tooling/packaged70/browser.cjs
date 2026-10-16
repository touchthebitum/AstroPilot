'use strict';
// Real DOM + HTTP integration. Observe responses; never replace backend results.
const fs = require('node:fs');
const path = require('node:path');
const cp = require('node:child_process');
const assert = require('node:assert/strict');
const {browserEnvironment} = require(process.env.PRODUCT_SOURCE + '/scripts/ci/night_chain/browser_environment.cjs');
assert(typeof WebSocket === 'function', 'Node with built-in WebSocket is required');
const root = process.env.CASE_ROOT, proof = process.env.CASE_PROOF;
const intent = process.env.UI_INTENT, url = process.env.NIGHT_CHAIN_URL;

assert(new URL(url).hostname === '127.0.0.1');
const chrome = process.env.CHROME_BINARY;
assert(chrome && fs.existsSync(chrome), 'Pinned testing browser is required');
const profile = path.join(proof, 'browser-profile');
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
    window.__ciTraffic = [];
    const realFetch = window.fetch.bind(window);
    window.fetch = async (...args) => {
      const response = await realFetch(...args);
      if (String(args[0]).startsWith('/v1/')) {
        const body = await response.clone().json().catch(() => null);
        window.__ciTraffic.push({url: String(args[0]), request: JSON.parse(args[1].body || 'null'), http: response.status, body});
      }
      return response;
    };
  `});
  const navigation = await send('Page.navigate', {url});
  fs.writeFileSync(path.join(proof,'navigation.json'),JSON.stringify(navigation));
  await waitFor(() => evaluate(`window.__ciTraffic.some(x=>x.url==='/v1/execution-sessions') && state.configuration?.configured`),'real configuration and saved sessions');
  const timezone = await evaluate(`(() => {
    const fmt = zone => new NightMeritTime.DateTimeFormat('fr-CH',{timeZone:zone,year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false,timeZoneName:'shortOffset'});
    const instant = new Date('2026-11-02T12:00:00Z');
    const winnipeg = fmt('America/Winnipeg').format(instant);
    const zurich = fmt('Europe/Zurich').format(new Date('2026-10-15T22:30:00Z'));
    return {id:NightMeritTime.id,winnipeg,zurich,winnipegHour:fmt('America/Winnipeg').formatToParts(instant).find(p=>p.type==='hour').value,
      zurichHour:fmt('Europe/Zurich').formatToParts(new Date('2026-10-15T22:30:00Z')).find(p=>p.type==='hour').value,
      nativeWinnipeg:new Intl.DateTimeFormat('fr-CH',{timeZone:'America/Winnipeg',hour:'2-digit',minute:'2-digit',hour12:false}).format(instant),
      winnipegOffset:NightMeritTime.offsetAt('America/Winnipeg',instant.getTime())};
  })()`);
  assert.equal(timezone.winnipegHour,'07');assert.equal(timezone.zurichHour,'00');
  assert.equal(timezone.winnipegOffset,-18000);
  const fixture=JSON.parse(fs.readFileSync(path.join(root,'fixture.json'),'utf8'));
  let record;
  if (process.env.BROWSER_MODE==='accept') {
    // Supply the production-API-generated deterministic view model directly to the real UI.
    // No HTTP response or packaged service is replaced. Actual clicks POST to frozen backend.
    await evaluate(`clearAcceptedMission();setCurrentFieldObservationDecision(${JSON.stringify(fixture.response)});renderDecision(${JSON.stringify(fixture.response)});true`);
    await waitFor(()=>evaluate(`Boolean(document.querySelector('#primary-intent-choice select'))`),'intent choice');
    await evaluate(`const choice=document.querySelector('#primary-intent-choice select');choice.value=${JSON.stringify(intent)};choice.dispatchEvent(new Event('change',{bubbles:true}));document.querySelector('#open-mission').click();true`);
    const accepted=await waitFor(()=>evaluate(`window.__ciTraffic.find(x=>x.url==='/v1/decision-selections')`),'frozen confirmation');
    assert.equal(accepted.http,200,JSON.stringify(accepted));assert.equal(accepted.body.status,'accepted');
    assert.equal(accepted.body.selected_acquisition_intent_id,intent);
    assert.equal(accepted.body.mission.site_timezone,fixture.zone);
    const filter=accepted.body.mission.selected_filter;
    assert.equal(filter.source,'authorized_optical_profile');assert.equal(filter.filter_type,intent==='ou4_oiii'?'OIII':'Ha');assert.equal(filter.bandwidth_nm,6.5);
    await waitFor(()=>evaluate(`document.querySelector('#mission-filter').textContent.includes(${JSON.stringify(filter.filter_type)})`),'real mission filter');
    const taskRows=await evaluate(`Array.from(document.querySelectorAll('#mission-tasks li'),r=>r.textContent)`);
    assert.equal(taskRows.length,4);assert(taskRows.every(r=>! /T-\d|Fin \+/.test(r)));
    const expected=await evaluate(`(() => {const m=${JSON.stringify(accepted.body.mission)};const fmt=new NightMeritTime.DateTimeFormat('fr-CH',{timeZone:m.site_timezone,year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false,timeZoneName:'shortOffset'});return [fmt.format(new Date(Date.parse(m.window_start)-30*60000)),fmt.format(new Date(Date.parse(m.window_start)-20*60000)),fmt.format(new Date(Date.parse(m.window_end)+10*60000))];})()`);
    assert(taskRows[0].includes(expected[0]));assert(taskRows[1].includes(expected[1]));assert(taskRows[3].includes(expected[2]));
    const replay=await evaluate(`(async()=>{const r=await fetch('/v1/decision-selections',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(${JSON.stringify(accepted.request)})});return {http:r.status,body:await r.json()};})()`);
    assert.equal(replay.http,200);assert.equal(replay.body.mission_id,accepted.body.mission_id);
    record={accepted,taskRows,expected,idempotent_confirmation:true,prepared_night:fixture.response.night_date,
      decision_generation:'source production API with synthetic weather; fixture view model supplied directly to UI',confirmation:'real DOM click to unmodified frozen backend'};
  } else {
    const missionId=process.env.MISSION_ID;
    await waitFor(()=>evaluate(`state.savedMissions.some(m=>m.mission_id===${JSON.stringify(missionId)})`),'persisted mission discovery');
    await evaluate(`document.querySelector('#saved-mission-choice').value=${JSON.stringify(missionId)};document.querySelector('#saved-mission-choice').dispatchEvent(new Event('change',{bubbles:true}));document.querySelector('#open-saved-mission').click();true`);
    await waitFor(()=>evaluate(`state.sessions.some(s=>s.execution.execution_id===${JSON.stringify(process.env.EXECUTION_ID)})`),'persisted session');
    await evaluate(`document.querySelector('#session-choice').value=${JSON.stringify(process.env.EXECUTION_ID)};document.querySelector('#session-choice').dispatchEvent(new Event('change',{bubbles:true}));true`);
    await waitFor(()=>evaluate(`document.querySelector('#session-status').textContent.includes('Crédit enregistré')`),'persisted credit UI');
    const session=await evaluate(`({status:document.querySelector('#session-status').textContent,after:document.querySelector('#session-after').textContent,intent:document.querySelector('#session-intent').textContent,filter:document.querySelector('#mission-filter').textContent,applyHidden:document.querySelector('#session-credit').hidden})`);
    assert(session.intent.includes(intent));assert(session.after.includes(intent==='sh2-129_ha'?'1 h 30':'0 h 15'),JSON.stringify(session));assert(session.applyHidden);
    record={session,restored_from_frozen_backend:true};
  }
  const shot=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:true});
  fs.writeFileSync(path.join(proof,'ui.png'),Buffer.from(shot.data,'base64'));
  fs.writeFileSync(path.join(proof,'ui.txt'),await evaluate('document.body.innerText'));
  const traffic=await evaluate('window.__ciTraffic');
  fs.writeFileSync(path.join(proof,'browser-result.json'),JSON.stringify({result:'PASS',intent,mode:process.env.BROWSER_MODE,timezone,...record,traffic,backend_response_replaced:false},null,2));
}
(async () => {
  try { await journey(); }
  catch(error) {
    if(ws && ws.readyState===WebSocket.OPEN) {try {
      fs.writeFileSync(path.join(proof,'failure-state.json'),JSON.stringify(await evaluate('({text:document.body.innerText,traffic:window.__ciTraffic})'),null,2));
      const shot=await send('Page.captureScreenshot',{format:'png'});fs.writeFileSync(path.join(proof,'failure.png'),Buffer.from(shot.data,'base64'));
    } catch(_) {} }
    throw error;
  }
  finally {
    clearTimeout(deadline);
    for (const entry of pending.values()) clearTimeout(entry.timer);
    if (ws) ws.close();
    await stopBrowser();
    fs.closeSync(log);
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
