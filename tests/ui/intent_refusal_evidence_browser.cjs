// Production UI + synthetic DTOs produced by the real eligibility/application pipeline.
const {chromium}=require('playwright');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {timeHeaders,timeData}=require('./timezone_fixture.cjs');
const fixtures=JSON.parse(fs.readFileSync(process.env.INTENT_REFUSAL_FIXTURES,'utf8'));
(async()=>{
 const browser=await chromium.launch({headless:true,channel:'chrome'});
 try {
  const page=await browser.newPage({timezoneId:'America/New_York'}),errors=[],requests=[];
  page.on('pageerror',e=>errors.push(e.message));
  page.on('request',r=>requests.push([r.method(),new URL(r.url()).pathname]));
  const web=path.resolve(__dirname,'../../astropilot/web');
  await page.route('https://intent-refusal.test/**',route=>{
   const p=new URL(route.request().url()).pathname;
   if(p==='/ui/timezone-data.js')return route.fulfill({headers:timeHeaders,body:timeData,contentType:'text/javascript'});
   if(p==='/v1/analysis-history')return route.fulfill({headers:timeHeaders,json:{items:fixtures.records,next_before:null}});
   const name=p==='/'?'index.html':p.startsWith('/ui/')?path.basename(p):'';
   if(name && fs.existsSync(path.join(web,name)))return route.fulfill({headers:timeHeaders,body:fs.readFileSync(path.join(web,name),'utf8').replaceAll('__ASTROPILOT_SESSION_TIMING__',''),contentType:name.endsWith('.js')?'text/javascript':name.endsWith('.css')?'text/css':'text/html'});
   return route.fulfill({headers:timeHeaders,status:503,json:{}});
  });
  async function setup(mode){
   await page.evaluate(mode=>{
    state.configuration={configured:true,site:{name:'Synthetic',timezone:'Europe/Zurich',latitude:46.75,longitude:6.55,bortle:4},projects:{M42:{hours:0,target_hours:15}}};
    state.configurationDraft={site:state.configuration.site,equipment:{preset_id:'samyang_183'},projects:state.configuration.projects};
    state.selectedProjectId='M42';state.currentDecision={decision_id:'live-sentinel'};applyUiMode(mode);
   },mode);
  }
  await page.goto('https://intent-refusal.test/');await page.waitForFunction(()=>appliedUiMode!==null);
  for(const mode of ['simple','pro'])for(const width of [390,768,1280]){
   await page.setViewportSize({width,height:900});await setup(mode);
   const before=await page.evaluate(()=>JSON.stringify([state.configuration,state.currentDecision,state.selectedProjectId]));
   for(const record of fixtures.records){
    await page.evaluate(payload=>showTonightUnavailable(payload),record.result);
    const stage=record.result.actionability_refusal?.refusal_stage;
    const scoped=record.decision_id.startsWith('scoped-');
    const noOverlap=scoped && !record.result.actionability_refusal.evidence_scope.evaluated_start;
    const title=mode==='simple' && stage ? (noOverlap?'Aucun créneau dans vos horaires':stage==='continuous_window_too_short'?'Le créneau favorable est trop court':'Pas de séance photo recommandée') : noOverlap?'Fenêtre hors de votre disponibilité':stage==='no_productive_slice'?'Aucune tranche productive':stage==='continuous_window_too_short'?'Fenêtre productive trop courte':'Créneau insuffisant pour ce projet';
    assert.equal(await page.locator('#message-title').innerText(),title);
    const technical=await page.locator('#message-technical').textContent();
    if(stage && mode==='simple'){
     const main=await page.locator('#message-body').innerText();
     assert(main.length<360);assert.doesNotMatch(main,/points|seuil|tranche|productive_slice/i);
     assert.equal(await page.locator('#message-details').evaluate(e=>e.open),false);
    }
    if(scoped && !noOverlap){
     assert.match(technical,/01:32 UTC\+1/);
     assert.doesNotMatch(technical,/00:32 UTC(?:[^+]|$)/);
    }
    if(scoped){
     assert.match(technical,/Disponibilité demandée/);assert.match(technical,/Fenêtre candidate/);
     if(noOverlap){assert.doesNotMatch(technical,/Meilleure tranche|Nuages : −/);}
     else{
      assert.match(technical,/Portion évaluée dans votre disponibilité/);
      assert.match(technical,/05:27/);assert.match(technical,/sans nouveau calcul à la minute/);
      assert.match(technical,/6 (portions|évaluées)/);
      assert.match(await page.locator('#message-window').innerText(),/05:27/);
      if(stage==='no_productive_slice')assert.match(technical,/20 %.*70 %/);
      else assert.match(await page.locator('#message-body').innerText(),/27 min.*60 min/);
     }
    }else if(stage==='no_productive_slice'){
     assert.match(technical,/55 %.*70 %/);assert.match(technical,/Lune : −40 points/);
     assert.match(technical,/Humidité : −5 points/);assert.doesNotMatch(technical,/Nuages : −/);
     assert.match(technical,/cause physique unique/);
    }else if(stage==='continuous_window_too_short'){
     assert.match(await page.locator('#message-body').innerText(),/30 min.*60 min/);
     assert.match(technical,/2 tranches productives sur 8/);assert.match(technical,/Vent : −10 points/);
     assert.doesNotMatch(technical,/Humidité : −|Nuages : −/);
    }else{
     assert.match(technical,/n’ont pas été conservés/);assert.doesNotMatch(technical,/Lune : −|Vent : −|Humidité : −/);
    }
    assert.equal(await page.locator('#message-details').evaluate(e=>e.open),mode==='pro');
    assert.equal(await page.locator('#open-mission').isVisible(),false);
    await page.locator('[data-open-analysis-history]').last().click();
    await page.waitForFunction(()=>document.querySelector('#analysis-history-list button'));
    await page.locator('#analysis-history-list button').nth(fixtures.records.indexOf(record)).click();
    const evidence=page.locator('#analysis-history-detail > details');
    assert.equal(await evidence.evaluate(e=>e.open),mode==='pro');
    if(mode==='simple'){
      const visible=await page.locator('#analysis-history-detail').innerText();
      assert.doesNotMatch(visible,/Nuages : −|Meilleure tranche|best_slice_score/);
      await evidence.locator('summary').first().click();
    }
    const archived=await page.locator('#analysis-history-detail').innerText();
    assert(archived.includes(title));
    if(scoped)assert.match(archived,/Fenêtre candidate/);
    if(!scoped && stage==='continuous_window_too_short')assert.match(archived,/30 min.*60 min/);
    if(!scoped && stage==='no_productive_slice')assert.match(archived,/55 %.*70 %/);
    if(!stage)assert.match(archived,/n’ont pas été conservés/);
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
    await page.locator('#analysis-history-close').click();
   }
   assert.equal(await page.evaluate(()=>JSON.stringify([state.configuration,state.currentDecision,state.selectedProjectId])),before);
  }
  await page.reload();await page.waitForFunction(()=>appliedUiMode!==null);await setup('simple');
  await page.locator('[data-open-analysis-history]').last().click();await page.waitForFunction(()=>document.querySelector('#analysis-history-list button'));
  await page.locator('#analysis-history-list button').first().click();
  assert.match(await page.locator('#analysis-history-detail').innerText(),/Pas de séance photo recommandée/);
  const record=fixtures.records.find(r=>r.decision_id==='scoped-outside_productive');
  if(record){
   const original=JSON.stringify(record);
   const labels=await page.evaluate(record=>{
    state.configuration.site.timezone='America/Los_Angeles';
    applyUiMode('simple');renderArchivedAnalysis(record);
    const historical=document.querySelector('#analysis-history-detail').innerText;
    const unknown=JSON.parse(JSON.stringify(record));delete unknown.request.location;unknown.result.weather_trust=null;
    renderArchivedAnalysis(unknown);
    return {historical,unknown:document.querySelector('#analysis-history-detail').innerText,
     beforeFold:refusalTimeLabel('2026-10-25T00:30:00Z','Europe/Zurich'),
     afterFold:refusalTimeLabel('2026-10-25T01:30:00Z','Europe/Zurich'),
     midnight:refusalTimeLabel('2026-10-27T23:30:00Z','Europe/Zurich')};
   },record);
   assert.match(labels.historical,/04:00.*05:27.*Europe\/Zurich/);
   assert.doesNotMatch(labels.historical,/Los_Angeles|UTC−/);
   assert.match(labels.unknown,/03:00.*04:27.*UTC/);
   assert.match(labels.beforeFold,/02:30 UTC\+2/);assert.match(labels.afterFold,/02:30 UTC\+1/);
   assert.match(labels.midnight,/28.10.2026 00:30 UTC\+1/);
   assert.equal(JSON.stringify(record),original);
  }
  assert(requests.every(([method])=>method==='GET'));assert.deepEqual(errors,[]);
  console.log(JSON.stringify({result:'PASS',synthetic:true,read_only:true,simple_pro:true,widths:[390,768,1280],reload_reread:true,no_forecast_recalculation:true}));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1)});
