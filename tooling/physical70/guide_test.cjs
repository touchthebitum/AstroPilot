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
const profile = path.join(root, 'browser-profile');
const log = fs.openSync(path.join(proof, 'browser.log'), 'w');
const env = browserEnvironment(process.env);
const child = {exitCode:0,signalCode:null,on(){}};
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
}, 480000);
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
        window.__ciTraffic.push({url: String(args[0]), request: JSON.parse(args[1]?.body || 'null'), http: response.status, body});
      }
      return response;
    };
  `});
  await send('Page.navigate',{url});
  await waitFor(()=>evaluate(`Boolean(document.querySelector('#choose'))`),'guide');
  await evaluate(`document.querySelector('#choose button').click();true`);
  await waitFor(()=>evaluate(`!document.querySelector('#journey').hidden && document.querySelector('#start').textContent.includes('T00:30')`),'guide starts public isolated site');
  fs.writeFileSync(path.join(proof,'guide-ready.json'),JSON.stringify(await evaluate('latest')));
  await waitFor(()=>fs.existsSync(path.join(proof,'request-restart')),'test sessions completed',180000);
  await waitFor(()=>evaluate(`latest.ready && !busy`),'guide observes both canonical credits');
  await evaluate(`document.querySelector('#before').checked=true;document.querySelector('#before').dispatchEvent(new Event('change'));document.querySelector('#restart').click();true`);
  await waitFor(()=>evaluate(`!document.querySelector('#replay').hidden && !busy`),'guide restart and replay',90000);
  fs.writeFileSync(path.join(proof,'guide-restarted.json'),JSON.stringify(await evaluate('latest')));
  await waitFor(()=>fs.existsSync(path.join(proof,'request-export')),'test sessions visually reopened',180000);
  await evaluate(`document.querySelector('#after').checked=true;document.querySelector('#after').dispatchEvent(new Event('change'));document.querySelector('#finish').click();true`);
  await waitFor(()=>evaluate(`!document.querySelector('#result').hidden && document.querySelector('#result-path').textContent.endsWith('.zip')`),'guide export',60000);
  const shot=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});fs.writeFileSync(path.join(proof,'guide.png'),Buffer.from(shot.data,'base64'));
  fs.writeFileSync(path.join(proof,'guide-finished.json'),JSON.stringify(await evaluate('latest')));
  await waitFor(()=>fs.existsSync(path.join(proof,'request-close')),'export verification',30000);
  await evaluate(`setTimeout(()=>document.querySelector('#result button').click(),100);true`);
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
