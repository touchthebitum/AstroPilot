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
  const file = {'/ui/app.js':'app.js','/ui/styles.css':'styles.css','/ui/help.js':'help.js'}[url.pathname];
  if (file) return route.fulfill({contentType:file.endsWith('.js')?'text/javascript':'text/css',body:fs.readFileSync(path.join(web,file),'utf8')});
  requests++;
  return route.fulfill({status:503,contentType:'application/json',body:'{}'});
 });
 const page = await context.newPage();
 const errors = []; page.on('pageerror', e => errors.push(e.message));
 await page.goto('http://nightmerit.test/');
 await page.waitForFunction(() => document.querySelector('#ui-mode').value === 'simple');

 await page.evaluate(() => {
  state.acceptedMission={mission_id:'mission-1',acquisitionIntentId:'private-intent-id'};
  state.sessions=[{execution:{execution_id:'execution-1',status:'completed',actual_start:null},
   acquisition_intent_id:'private-intent-id', evidence:[],credit:null,historical_baseline_seconds:3600,
   historical_baseline_confirmed:false,acquired_before_seconds:3600,session_credit_seconds:0,
   acquired_after_seconds:3600,current_acquired_seconds:3600,target_hours:2,remaining_hours:1}];
  state.activeSessionId='execution-1';
  renderSession(); ui.mission.showModal();
 });
 for (const mode of ['simple','pro']) for (const width of [390,1280]) {
  await page.setViewportSize({width,height:900});
  await page.evaluate(mode=>applyUiMode(mode),mode);
  for (const step of ['active','duration','credit','credited','interrupted','unconfirmed','ready','none']) {
   await page.evaluate(step=>{
    state.activeSessionId=step==='none'?null:'execution-1';
    const s=state.sessions[0];
    s.execution.status={active:'in_progress',interrupted:'interrupted',unconfirmed:'unconfirmed',ready:'not_started'}[step]||'completed';
    s.evidence=['credit','credited'].includes(step)?[{category:'acquisition',usable_integration_duration:1800}]:[];
    s.credit=step==='credited'?{execution_id:'execution-1'}:null;
    renderSession();
   },step);
   const primary={active:'session-complete',duration:'session-record-evidence',credit:'session-apply-credit',credited:'session-start',interrupted:'session-start',ready:'session-start',none:'session-start'}[step];
   assert.deepEqual(await page.locator('.session-panel .primary-button:visible').evaluateAll(es=>es.map(e=>e.id)),primary?[primary]:[]);
   assert.equal(await page.locator('#session-intent').isVisible(),mode==='pro');
   if(mode==='simple') assert.doesNotMatch(await page.locator('.session-panel').innerText(),/private-intent-id|execution-1|intent/i);
   if(step==='credit') {
    assert.equal(await page.locator('#session-credit-intent').isVisible(),mode==='pro');
    assert.equal(await page.locator('#session-apply-credit').innerText(),'Ajouter cette durée à mon avancement');
    assert.equal(await page.locator('#session-baseline-confirm-wrap').isVisible(),true);
   }
   assert.equal(await page.locator('#mission-dialog').evaluate(e=>e.scrollWidth<=e.clientWidth),true);
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
  }
  assert.equal(await page.locator('#session-complete').textContent(),'Terminer la session');
  assert.equal(await page.locator('#session-interrupt').textContent(),'Interrompre la session');
 }
 await page.evaluate(()=>ui.mission.close());
 const before=requests;
 await page.locator('#outcome-reopen').click();
 await page.locator('#recent-observations-message').waitFor({state:'visible'});
 assert.equal(await page.locator('#recent-observations-message').innerText(),'Aucune observation enregistrée récemment.');
 assert.equal(requests,before);
 assert.deepEqual(errors,[]);
 await browser.close();
 console.log('Session completion: Simple/Pro, 390/1280, eight states and empty observations passed.');
})().catch(e=>{console.error(e);process.exit(1)});
