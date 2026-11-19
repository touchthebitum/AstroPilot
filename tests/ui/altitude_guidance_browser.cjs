// Real Chrome, production UI, real astronomy fixture; isolated synthetic profile.
const {chromium}=require('playwright');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {timeHeaders,timeData}=require('./timezone_fixture.cjs');
const fixture=JSON.parse(fs.readFileSync(process.env.ALTITUDE_GUIDANCE_FIXTURE,'utf8'));
(async()=>{
 const browser=await chromium.launch({headless:true,channel:'chrome'});
 try {
  const page=await browser.newPage({timezoneId:'America/New_York'}),errors=[],requests=[];
  await page.clock.install({time:new Date('2026-10-27T12:00:00Z')});
  page.on('pageerror',e=>errors.push(e.message));
  page.on('request',r=>requests.push({method:r.method(),path:new URL(r.url()).pathname,body:r.postDataJSON()}));
  const web=path.resolve(__dirname,'../../astropilot/web');let responseMode='normal',held;
  await page.route('https://altitude.test/**',async route=>{
   const p=new URL(route.request().url()).pathname;
   if(p==='/ui/timezone-data.js')return route.fulfill({headers:timeHeaders,body:timeData,contentType:'text/javascript'});
   if(p.endsWith('/altitude-guidance')){
    if(responseMode==='held')await new Promise(resolve=>held=resolve);
    const data=structuredClone(fixture);
    if(responseMode==='none'){data.intervals=[];data.status='no_altitude_window';}
    if(responseMode==='short')data.intervals=data.intervals.map(i=>({...i,can_analyze:false,duration_minutes:30}));
    if(responseMode==='mismatch')data.latitude=0;
    return route.fulfill({headers:timeHeaders,json:data}).catch(()=>{});
   }
   if(p==='/v1/tonight')return route.fulfill({headers:timeHeaders,json:{status:'no_candidate',target_refusal:{code:'target_window_unavailable'}}});
   const name=p==='/'?'index.html':p.startsWith('/ui/')?path.basename(p):'';
   if(name&&fs.existsSync(path.join(web,name)))return route.fulfill({headers:timeHeaders,body:fs.readFileSync(path.join(web,name),'utf8').replaceAll('__ASTROPILOT_SESSION_TIMING__',''),contentType:name.endsWith('.js')?'text/javascript':name.endsWith('.css')?'text/css':'text/html'});
   return route.fulfill({headers:timeHeaders,status:503,json:{}});
  });
  await page.goto('https://altitude.test/');await page.waitForFunction(()=>appliedUiMode!==null);
  async function setup(mode='simple'){
   await page.evaluate(mode=>{
    state.configuration={configured:true,site:{name:'Buttes',timezone:'Europe/Zurich',latitude:46.7508,longitude:6.5495,bortle:3},projects:{M42:{hours:0,target_hours:15}}};
    state.configurationDraft={site:state.configuration.site,equipment:{preset_id:'samyang_183'},projects:state.configuration.projects};
    state.discoveryMode=false;state.selectedProjectId='M42';state.currentDecision={decision_id:'read-sentinel'};state.availability={mode:'all_night'};
    applyUiMode(mode);setView('availability');
    document.querySelector('input[name="availability-mode"][value="all_night"]').checked=true;
    renderAvailabilityTimezone();
   },mode);
  }
  for(const mode of ['simple','pro'])for(const width of [320,390,768,1280]){
   await page.setViewportSize({width,height:850});await setup(mode);
   const before=await page.evaluate(()=>JSON.stringify([state.configuration,state.currentDecision,state.availability,state.selectedProjectId]));
   await page.locator('#availability-altitude-guidance').click();
   await page.locator('#altitude-guidance-result').waitFor({state:'visible'});
   assert.match(await page.locator('#altitude-guidance-summary').innerText(),/30°/);
   assert.match(await page.locator('#altitude-guidance-status').innerText(),/Europe\/Zurich/);
   assert.match(await page.locator('#altitude-guidance-intervals').innerText(),/28\.10\.2026.*01:31/);
   assert.equal(await page.locator('#altitude-guidance-chart polyline').count(),1);
   assert.equal(await page.locator('#altitude-guidance-dialog').evaluate(e=>e.scrollWidth<=e.clientWidth),true);
   await page.locator('#altitude-guidance-close').click();
   assert.equal(await page.locator('#altitude-guidance-dialog').evaluate(e=>e.open),false);
   assert.equal(await page.evaluate(()=>JSON.stringify([state.configuration,state.currentDecision,state.availability,state.selectedProjectId])),before);
   assert(requests.every(r=>r.method==='GET'));
  }
  for(const mode of ['none','short','mismatch']){
   responseMode=mode;await setup();await page.locator('#availability-altitude-guidance').click();
   await page.waitForFunction(()=>!document.querySelector('#altitude-guidance-status').textContent.includes('Calcul de la hauteur'));
   assert.equal(await page.locator('#altitude-guidance-intervals button').count(),0);
   if(mode==='none')assert.match(await page.locator('#altitude-guidance-intervals').innerText(),/Aucun intervalle/);
   if(mode==='short')assert.match(await page.locator('#altitude-guidance-intervals').innerText(),/60 minutes/);
   if(mode==='mismatch')assert.match(await page.locator('#altitude-guidance-status').innerText(),/configuration du site a changé/);
   await page.keyboard.press('Escape');
   assert.equal(await page.locator('#altitude-guidance-dialog').evaluate(e=>e.open),false);
  }
  responseMode='held';await setup();await page.locator('#availability-altitude-guidance').click();
  await page.waitForFunction(()=>document.querySelector('#altitude-guidance-dialog').open);
  await page.evaluate(()=>{state.configurationGeneration++;});
  while(!held)await new Promise(resolve=>setTimeout(resolve,10));held();
  await page.waitForLoadState('networkidle');
  assert.equal(await page.locator('#altitude-guidance-result').isVisible(),false);
  await page.locator('#altitude-guidance-close').click();
  responseMode='normal';await setup();
  await page.evaluate(()=>showTonightUnavailable({status:'no_candidate',target_refusal:{code:'target_below_minimum_altitude',minimum_altitude_deg:30}}));
  await page.locator('#message-altitude-guidance').click();await page.locator('#altitude-guidance-result').waitFor({state:'visible'});
  if(process.env.ALTITUDE_SCREENSHOT)await page.screenshot({path:process.env.ALTITUDE_SCREENSHOT});
  await page.locator('#altitude-guidance-intervals button').first().click();
  await page.waitForFunction(()=>state.requestingRecommendation===false);
  const writes=requests.filter(r=>r.method!=='GET');assert.equal(writes.length,1);
  assert.equal(writes[0].path,'/v1/tonight');assert.equal(writes[0].body.selected_project_id,'M42');
  assert.deepEqual(writes[0].body.availability,{mode:'fixed_window',start:fixture.intervals[0].start,end:fixture.intervals[0].end});
  assert.equal(await page.evaluate(()=>state.selectedProjectId),'M42');
  await page.evaluate(()=>{state.discoveryMode=true;setView('availability');});
  assert.equal(await page.locator('#availability-altitude-guidance').isVisible(),false);
  assert.deepEqual(errors,[]);
  console.log(JSON.stringify({result:'PASS',real_chrome:true,astronomy_fixture:true,synthetic_profile:true,widths:[320,390,768,1280],modes:['simple','pro'],read_only_until_explicit_analysis:true,target_preserved:true,stale_response_ignored:true,no_automatic_mission:true}));
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exit(1)});
