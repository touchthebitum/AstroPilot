// Run with the bundled Node runtime and NODE_PATH pointing to bundled packages.
const {chromium} = require('playwright');
const fs = require('fs');
const path = require('path');
const assert = require('node:assert/strict');
(async () => {
 const web = path.resolve(__dirname, '../../astropilot/web');
 const browser = await chromium.launch({headless:true, channel:'chrome'});
 const context = await browser.newContext();
 let requests = 0;
 await context.route('http://nightmerit.test/**', route => {
  const url = new URL(route.request().url());
  if (url.pathname === '/') return route.fulfill({contentType:'text/html',body:fs.readFileSync(path.join(web,'index.html'),'utf8')});
  const file = {'/ui/app.js':'app.js','/ui/styles.css':'styles.css'}[url.pathname];
  if (file) return route.fulfill({contentType:file.endsWith('.js')?'text/javascript':'text/css',body:fs.readFileSync(path.join(web,file),'utf8')});
  requests++;
  return route.fulfill({status:503,contentType:'application/json',body:'{}'});
 });
 const page = await context.newPage();
 const errors = []; page.on('pageerror', e => errors.push(e.message));
 await page.goto('http://nightmerit.test/');
 await page.waitForFunction(() => document.querySelector('#ui-mode').value === 'simple');
 await page.evaluate(() => {
  state.currentDecision = {decision_id:'retained-decision'};
  state.acceptedMission = {mission_id:'retained-mission'};
  state.fieldObservationLock = {pending:{observation_id:'retained-pending'}};
  window.modeSnapshot = {decision:state.currentDecision,mission:state.acceptedMission,lock:state.fieldObservationLock,
   token:state.outcomeToken,historyGeneration:historyState.generation};
  document.querySelector('#field-observation-dialog').showModal();
  document.querySelector('#observation-hfr').value='2.15';
  document.querySelector('#observation-guiding').value='0.63';
  document.querySelector('#observation-clouds').value='few';
  renderOutcomeEvaluation({observation_id:'test-id',status:'partial',results:[],reasons:[{code:'unknown'}],weather_traceability:{provider_id:'long-provider'.repeat(30),requested_location:{latitude:46.12,longitude:7.34},grid_location:{latitude:46.13,longitude:7.35,altitude_m:1200}}});
 });
 assert.equal(await page.locator('#outcome-result').innerText(), 'Partiellement comparable\nRaison non reconnue.');
 const count = requests;
 for (const mode of ['pro','simple']) {
  await page.evaluate(mode => {const control=document.querySelector('#ui-mode');control.value=mode;control.dispatchEvent(new Event('change'));},mode);
  assert.equal(await page.inputValue('#observation-hfr'),'2.15');
  assert.equal(await page.inputValue('#observation-guiding'),'0.63');
  assert.equal(await page.inputValue('#observation-clouds'),'few');
  assert.equal(await page.locator('.observation-advanced').evaluate(e=>e.open),mode==='pro');
  assert.equal(await page.locator('#outcome-trace').evaluate(e=>e.parentElement.open),mode==='pro');
 }
 assert.equal(requests,count);
 assert.equal(await page.evaluate(() => state.currentDecision===modeSnapshot.decision && state.acceptedMission===modeSnapshot.mission &&
 state.fieldObservationLock===modeSnapshot.lock && state.outcomeToken===modeSnapshot.token && historyState.generation===modeSnapshot.historyGeneration),true);
 for (const mode of ['simple','pro']) for (const width of [390,1280]) {
  await page.evaluate(mode=>applyUiMode(mode),mode);
  await page.setViewportSize({width,height:900});
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
  assert.equal(await page.locator('#field-observation-dialog').evaluate(e=>e.scrollWidth<=e.clientWidth),true);
 }
 await page.evaluate(()=>{ document.querySelector('#field-observation-dialog').close(); applyUiMode('simple'); });
 await page.selectOption('#ui-mode','pro');
 await page.reload();
 assert.equal(await page.inputValue('#ui-mode'),'pro');
 const second = await context.newPage();await second.goto('http://nightmerit.test/');
 await page.selectOption('#ui-mode','simple');
 await second.waitForFunction(()=>document.querySelector('#ui-mode').value==='simple');
 await page.evaluate(()=>localStorage.setItem('nightmerit.ui-mode.v1','invalid'));await page.reload();
 assert.equal(await page.inputValue('#ui-mode'),'simple');
 await page.evaluate(()=>{
  document.querySelector('#history-dialog').showModal();
  document.querySelector('#history-filters [name="provider"]').value='retained';
  renderOutcomeHistory({rows:[{observed_at_utc:'2026-10-04T20:00:00Z',site:{latitude:46.12,longitude:7.34},
    context:{site_name:'Site',target:'Cible',imaging_field_id:'field-id',acquisition_intent_id:'intent-id'},
    mode:'decision_only',status:'partial',supersession:'active',results:[{variable:'temperature_c',status:'comparable',forecast_value:12,observed_value:10,unit:'°C',signed_error:2,absolute_error:2}],
    compared_providers:['test-provider'],evidence_providers:['test-provider']}],statistics:null,next_cursor:null,completeness:'degraded',certification:'statistics_suspended',readable_filtered_rows:1,diagnostics:[]});
 });
 for (const mode of ['pro','simple']) {
  await page.evaluate(mode=>applyUiMode(mode),mode);
  assert.equal(await page.locator('#history-filters details').evaluate(e=>e.open),mode==='pro');
  assert.equal(await page.inputValue('#history-filters [name="provider"]'),'retained');
  assert.equal(await page.locator('#history-table th[data-pro-only]').first().isVisible(),mode==='pro');
  assert.equal(await page.locator('#history-table details').evaluate(e=>e.open),mode==='pro');
 }
 for (const mode of ['simple','pro']) for (const width of [390,1280]) {
  await page.evaluate(mode=>applyUiMode(mode),mode);
  await page.setViewportSize({width,height:900});
  assert.equal(await page.locator('#history-dialog').evaluate(e=>e.scrollWidth<=e.clientWidth),true);
 }
 assert.deepEqual(errors,[]);
 console.log('Browser checks passed: persistence, multi-tab, draft/guards/filter retention, disclosures, 390/1280px.');
 await browser.close();
})().catch(e=>{console.error(e);process.exit(1);});
