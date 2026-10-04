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

 // Exercise the real consultation and real toggles, including replacement of old messages.
 await page.evaluate(async () => {
  window.savedNetworkRequest=fieldObservationNetworkRequest;
  state.outcomeContext={decision_id:'d',execution_id:null};
  state.outcomeObservationId='obs';
  state.visibleObservationsForContext=[{observation_id:'obs',decision_id:'d'}];
  fieldObservationNetworkRequest=async (_url,_options,consume)=>consume({
   ok:true,json:async()=>({evaluation_id:'e',observation_id:'obs',decision_id:'d',execution_id:null,
    version:'outcome_evaluation.v1',comparison_id:'c',computed_at_utc:'2026-10-04T20:00:00Z',
    status:'partial',results:[],reasons:[{code:'forecast_variable_unavailable',variable:null}],
    assessment:null,evidence_reference:null})
  });
 });
 for (const width of [390,1280]) {
  await page.setViewportSize({width,height:900});
  for (const kind of ['unknown','superseded','clean','error']) {
   await page.evaluate(async kind=>{
    applyUiMode('simple');
    state.outcomeLineageStatus=kind==='unknown'?'pending':'ready';
    state.allObservationsForDecision=[{observation_id:'obs',decision_id:'d'},
     ...(kind==='superseded'?[{observation_id:'new',decision_id:'d',supersedes_observation_id:'obs'}]:[])];
    if(kind==='error') fieldObservationNetworkRequest=async()=>{throw Error('unavailable');};
    await consultOutcomeEvaluation(false);
    renderSavedFieldObservations();
   },kind);
   const before=await page.locator('#outcome-result').innerText();
   if(kind==='unknown') assert.match(before,/Supersession inconnue : création bloquée\.\nPartiellement comparable/);
   if(kind==='superseded') assert.match(before,/Historique \/ remplacée.*\nPartiellement comparable/);
   if(kind==='clean') {assert.match(before,/^Partiellement comparable/);assert.doesNotMatch(before,/Supersession inconnue|Historique \/ remplacée/);}
   if(kind==='error') assert.match(before,/Comparaison indisponible/);
   for(const mode of ['pro','simple']) {
    await page.evaluate(mode=>applyUiMode(mode),mode);
    assert.equal(await page.locator('#outcome-result').innerText(),before);
    if(['unknown','superseded'].includes(kind)) assert.equal(await page.locator('#outcome-compare').isDisabled(),true);
   }
   // Reinstall the successful fixture for the next width.
   if(kind==='error') await page.evaluate(()=>fieldObservationNetworkRequest=async (_u,_o,consume)=>consume({
    ok:true,json:async()=>({evaluation_id:'e',observation_id:'obs',decision_id:'d',execution_id:null,
     version:'outcome_evaluation.v1',comparison_id:'c',computed_at_utc:'2026-10-04T20:00:00Z',
     status:'partial',results:[],reasons:[{code:'forecast_variable_unavailable',variable:null}],assessment:null,evidence_reference:null})
   }));
  }
 }
 await page.evaluate(()=>fieldObservationNetworkRequest=window.savedNetworkRequest);

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
 await page.evaluate(() => {
  applyUiMode('simple');
  const details = document.querySelector('#history-filters details');
  details.open = true;
  window.dispatchEvent(new StorageEvent('storage', {key:UI_MODE_KEY,newValue:'simple'}));
  if (!details.open) throw Error('same mode closed filters');
  window.dispatchEvent(new StorageEvent('storage', {key:UI_MODE_KEY,newValue:'pro'}));
  if (!details.open) throw Error('Pro did not open filters');
  details.open = false;
  window.dispatchEvent(new StorageEvent('storage', {key:UI_MODE_KEY,newValue:'pro'}));
  if (details.open) throw Error('repeated Pro event churn');
  applyUiMode('simple');
  state.configuration = {site:{latitude:46.12,longitude:7.34}};
  document.querySelector('#history-current-site').click();
 });
 assert.match(await page.locator('#history-filter-summary').innerText(),/ce site · source : retained/);
 await page.evaluate(() => loadOutcomeHistory());
 assert.match(await page.locator('#history-filter-summary').innerText(),/ce site/);
 assert.equal(await page.locator('#history-filters details').evaluate(e=>e.open),false);
 await page.locator('#history-filter-summary').click();
 assert.equal(await page.locator('#history-filters details').evaluate(e=>e.open),true);
 await page.evaluate(() => {
  const form=document.querySelector('#history-filters');
  form.reset(); updateHistoryFilterSummary();
 });
 assert.equal(await page.locator('#history-filter-summary').innerText(),'Filtres actifs : observations actuelles — Modifier');
 for (const mode of ['simple','pro']) for (const width of [390,1280]) {
  await page.evaluate(() => {
   const form=document.querySelector('#history-filters');
   form.elements.provider.value='x'.repeat(200);form.elements.mode.value='execution';
   form.elements.status.value='partial';form.elements.include_superseded.checked=true;
  });
  await page.evaluate(mode=>applyUiMode(mode),mode);
  await page.setViewportSize({width,height:900});
  if (mode==='simple') assert.match(await page.locator('#history-filter-summary').innerText(),/source : x{200} · exécution · couverture partielle · observations remplacées incluses — Modifier/);
  assert.equal(await page.locator('#history-dialog').evaluate(e=>e.scrollWidth<=e.clientWidth),true);
  assert.equal(await page.locator('#history-filter-summary').evaluate(e=>e.scrollWidth<=e.clientWidth),true);
  if(mode==='simple') {await page.locator('#history-filters details').evaluate(e=>e.open=false);await page.locator('#history-filter-summary').click();assert.equal(await page.locator('#history-filters details').evaluate(e=>e.open),true);}
 }

 // Real storage delivery from a second Chrome tab while catalogue/selection await.
 const other = await context.newPage();
 await other.goto('http://nightmerit.test/');
 await page.evaluate(() => {window.lastModeEvent=undefined;window.addEventListener('storage',e=>{if(e.key===UI_MODE_KEY) window.lastModeEvent=e.newValue;});});
 for (const [initial, value, expected] of [
  ['simple','pro','pro'], ['pro','simple','simple'],
  ['pro','pro','pro'], ['pro','invalid','simple'], ['simple','simple','simple']
 ]) {
  await page.evaluate(initial => {
   applyUiMode(initial);
   state.fieldObservationLock = null;
   state.fieldObservationContextInvalid = false;
   state.observationBusy = false;
   state.configuration = {site:{latitude:46.12,longitude:7.34,timezone:'Europe/Zurich'}};
   state.fieldObservationDraftContext = {source:'catalogue',decision_id:null,execution_id:null,timezone:'Europe/Zurich'};
   state.recentDecisions = {open:true,items:[],cursor:null,extension:1};
   document.querySelector('#observation-observed-at').value='2026-10-04T22:00';
   if (!ui.observation.open) ui.observation.showModal();
   fieldObservationNetworkRequest = () => new Promise(resolve => window.releaseCatalogue=resolve);
   window.cataloguePromise = loadRecentDecisions();
   window.businessSnapshot = {
    generation:recentDecisionsGeneration,operation:fieldObservationOperationGeneration,
    draft:state.fieldObservationDraftContext,catalogue:state.recentDecisions,lock:state.fieldObservationLock
   };
  }, initial);
  // Force a write even for same-mode events; initial storage event is drained first.
  await other.evaluate(initial => localStorage.setItem(UI_MODE_KEY,initial),initial);
  await page.waitForFunction(initial => document.querySelector('#ui-mode').value===initial,initial);
  await page.evaluate(() => window.lastModeEvent=undefined);
  await other.evaluate(value => {localStorage.removeItem(UI_MODE_KEY);localStorage.setItem(UI_MODE_KEY,value);},value);
  await page.waitForFunction(value => window.lastModeEvent===value,value);
  assert.equal(await page.inputValue('#ui-mode'),expected);
  await page.evaluate(async () => {
   if (recentDecisionsGeneration!==businessSnapshot.generation || fieldObservationOperationGeneration!==businessSnapshot.operation
    || state.fieldObservationDraftContext!==businessSnapshot.draft || state.recentDecisions!==businessSnapshot.catalogue
    || state.fieldObservationLock!==businessSnapshot.lock) throw Error('UI event mutated business state');
   if (document.querySelector('#observation-catalogue-status').textContent!=='Chargement des décisions…') throw Error('loading ownership lost');
   releaseCatalogue({items:[{decision_id:'valid-catalogue-decision',night_date:'2026-10-04'}],complete:true});
   await cataloguePromise;
  });
  assert.equal(await page.locator('#observation-decision-candidates button').count(),1);
  assert.match(await page.locator('#observation-catalogue-status').textContent(),/Choisissez explicitement/);
  await page.evaluate(() => {
   canonicalFieldObservationContextAvailable = () => new Promise(resolve => window.releaseSelection=resolve);
   window.selectionPromise = selectRecentDecision(state.recentDecisions.items[0]);
   window.selectionGeneration = recentDecisionsGeneration;
  });
  await other.evaluate(expected => localStorage.setItem(UI_MODE_KEY,expected==='pro'?'simple':'pro'),expected);
  await page.waitForFunction(expected => document.querySelector('#ui-mode').value!==(expected),expected);
  await page.evaluate(async () => {
   if (recentDecisionsGeneration!==selectionGeneration) throw Error('UI event invalidated selection');
   releaseSelection(true); await selectionPromise;
   if (state.fieldObservationDraftContext.decision_id!=='valid-catalogue-decision') throw Error('selection rejected');
  });
 }
 // Unrelated keys ignored; actual pending/lock/clear still invalidate stale replies.
 await page.evaluate(async () => {
  for (const key of ['unrelated.preference', FIELD_OBSERVATION_PENDING_PREFIX+'negative', FIELD_OBSERVATION_LOCK_KEY, null]) {
   state.fieldObservationLock=null; state.fieldObservationContextInvalid=false;
   state.fieldObservationDraftContext={source:'catalogue',decision_id:null,execution_id:null,timezone:'Europe/Zurich'};
   state.recentDecisions={open:true,items:[],cursor:null,extension:1};
   const pending=loadRecentDecisions(); const generation=recentDecisionsGeneration;
   window.dispatchEvent(new StorageEvent('storage',{key,newValue:null,storageArea:localStorage}));
   if ((recentDecisionsGeneration===generation)!==(key==='unrelated.preference')) throw Error('storage key guard incorrect');
   releaseCatalogue({items:[{decision_id:'negative'}],complete:true}); await pending;
   if (state.recentDecisions.items.length!==(key==='unrelated.preference'?1:0)) throw Error('stale response accepted');
  }
 });
 await other.close();
 assert.deepEqual(errors,[]);
 console.log('Browser checks passed: persistence, multi-tab, draft/guards/filter retention, disclosures, 390/1280px.');
 await browser.close();
})().catch(e=>{console.error(e);process.exit(1);});
