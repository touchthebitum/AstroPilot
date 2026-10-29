const {timeHeaders,timeData}=require('./timezone_fixture.cjs');
const {chromium}=require('playwright');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
(async()=>{
 const web=path.resolve(__dirname,'../../astropilot/web');
 const browser=await chromium.launch({headless:true,chromiumSandbox:true,
  ...(process.env.NIGHTMERIT_TEST_CHROME?{executablePath:process.env.NIGHTMERIT_TEST_CHROME}:{channel:'chrome'})});
 try{
  const context=await browser.newContext({timezoneId:'America/New_York'}),writes=[];let sessions=[],fail=false;
  await context.route('http://nightmerit.test/**',async route=>{
   const url=new URL(route.request().url()),method=route.request().method();
   if(method!=='GET')writes.push({path:url.pathname,body:route.request().postDataJSON()});
   if(url.pathname==='/ui/timezone-data.js')return route.fulfill({headers:timeHeaders,contentType:'text/javascript',body:timeData});
   if(url.pathname==='/')return route.fulfill({headers:timeHeaders,contentType:'text/html',body:fs.readFileSync(path.join(web,'index.html'),'utf8').replaceAll('__ASTROPILOT_SESSION_TIMING__','').replaceAll('__ASTROPILOT_ASSET_TOKEN__','review')});
   const file={'/ui/timezone-authority.js':'timezone-authority.js','/ui/app.js':'app.js','/ui/styles.css':'styles.css'}[url.pathname];
   if(file)return route.fulfill({headers:timeHeaders,contentType:file.endsWith('.js')?'text/javascript':'text/css',body:fs.readFileSync(path.join(web,file),'utf8')});
   if(url.pathname==='/v1/missions/mission/executions')return route.fulfill({headers:timeHeaders,json:sessions});
   if(url.pathname==='/v1/tonight')return route.fulfill({headers:timeHeaders,status:fail?503:200,json:fail?{detail:{code:'weather_unavailable'}}:{status:'no_candidate',creation_refusal:'no_eligible_acquisition_intent'}});
   return route.fulfill({headers:timeHeaders,status:503,json:{}});
  });
  const page=await context.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto('http://nightmerit.test/');await page.waitForFunction(()=>state.view==='configuration_error');
  const config={configured:true,profile_revision:2,site:{name:'TEST FICTIF',latitude:46.88,longitude:6.54,bortle:4,timezone:'Europe/Zurich'},active_equipment_id:'samyang_183',available_equipment:[],preset_equipment:[],projects:{'Sh2-129':{hours:0,target_hours:20,imaging_field_id:'sh2-129_ou4',acquisition_intent_targets:[{acquisition_intent_id:'ou4_oiii',target_hours:20}],acquisition_intent_progress:[{acquisition_intent_id:'ou4_oiii',acquired_frames:145,exposure_seconds:300}]}}};
  const start=new Date(Date.now()+86400000).toISOString(),end=new Date(Date.now()+93600000).toISOString();
  const mission={mission_id:'mission',decision_id:'decision',selection_id:'selection',target:'Sh2-129',window_start:start,window_end:end,site_timezone:'Europe/Zurich',recommended_hours:2,equipment:[],tasks:[]};
  async function open({persisted=false,past=false,missing=false,otherSite=false,window=null}={}){
   await page.evaluate(({config,mission,persisted,past,missing,otherSite,window})=>{
    state.configuration=structuredClone(config);state.configurationDraft=draftFromConfiguration(state.configuration);
    state.decisionSiteReloadRequired=false;state.selectedProjectId='unrelated-project';state.discoveryMode=true;
    state.availability={mode:'all_night'};state.sessionBusy=false;state.sessionWriteUncertain=false;
    state.acceptedMission={mission_id:'mission',selectedCatalogKey:missing?'missing':'Sh2-129',acquisitionIntentId:'ou4_oiii',mission:structuredClone(mission),acceptedSiteGeneration:state.decisionSiteGeneration,acceptedSiteFingerprint:decisionSiteFingerprint()};
    if(persisted)delete state.acceptedMission.acceptedSiteFingerprint;
    if(otherSite){state.configuration.site.latitude=47;state.configurationDraft=draftFromConfiguration(state.configuration);}
    if(window)Object.assign(state.acceptedMission.mission,window);
    if(past){state.acceptedMission.mission.window_start='2020-01-01T20:00:00Z';state.acceptedMission.mission.window_end='2020-01-01T22:00:00Z';}
    setView('availability');renderMission(state.acceptedMission.mission);ui.mission.showModal();
   },{config,mission,persisted,past,missing,otherSite,window});
   await page.waitForFunction(()=>state.missionConditionsReady);
  }
  for(const mode of ['simple','pro'])for(const width of [390,768,1280,1600]){
   await page.setViewportSize({width,height:900});await page.evaluate(mode=>applyUiMode(mode),mode);await open();
   const before=writes.length;
   await page.getByRole('button',{name:'Vérifier les conditions avant de commencer',exact:true}).scrollIntoViewIfNeeded();
   assert.equal(await page.evaluate(()=>document.querySelector('#mission-dialog').scrollWidth<=document.querySelector('#mission-dialog').clientWidth),true);
   if(mode==='simple'&&width===1280&&process.env.NIGHTMERIT_TEST_SCREENSHOT)await page.screenshot({path:process.env.NIGHTMERIT_TEST_SCREENSHOT});
   await page.locator('#mission-check-conditions').click();
   assert.equal(writes.length,before,'opening a recheck never starts an analysis');
   assert.match(await page.locator('#availability-title').innerText(),/Vérifier les conditions de ma mission/);
   assert.match(await page.locator('#mission-recheck-summary').innerText(),/Mission enregistrée.*Sh2-129/);
   await page.locator('#request-recommendation').click();await page.waitForFunction(()=>!state.requestingRecommendation);
   assert.deepEqual(writes.slice(before),[{path:'/v1/tonight',body:{availability:{mode:'fixed_window',start,end},selected_project_id:'Sh2-129'}}]);
   assert.equal(await page.locator('#mission-dialog').isVisible(),false);
   assert.equal(await page.evaluate(()=>state.discoveryMode),false);
   assert.equal(await page.evaluate(()=>state.selectedProjectId),'Sh2-129');
   assert.deepEqual(await page.evaluate(()=>state.configuration.projects),config.projects);
  }
  for(const options of [{persisted:true},{past:true},{otherSite:true}]){
   await open(options);const before=writes.length;await page.locator('#mission-check-conditions').click();
   assert.equal(writes.length,before);assert.equal(await page.evaluate(()=>state.view),'availability');
   assert.equal(await page.locator('#availability-error').isVisible(),false);
   assert.notEqual(await page.locator('#availability-start').inputValue(),'');
   assert.notEqual(await page.locator('#availability-end').inputValue(),'');
   if(options.past)assert.match(await page.locator('#availability-start').inputValue(),/^2020-01-01/);
   assert.match(await page.locator('#request-recommendation').innerText(),/Vérifier les conditions sur ce créneau/);
   assert.equal(await page.evaluate(()=>state.acceptedMission.mission_id),'mission');
  }
  await open({persisted:true});
  await page.evaluate(()=>{state.configuration.site.timezone=null;state.configurationDraft=draftFromConfiguration(state.configuration);});
  let unchangedWrites=writes.length;await page.locator('#mission-check-conditions').click();
  assert.equal(writes.length,unchangedWrites);
  assert.match(await page.locator('#availability-error').innerText(),/fuseau horaire/);
  await open({persisted:true,window:{window_start:null}});unchangedWrites=writes.length;
  await page.locator('#mission-check-conditions').click();
  assert.equal(writes.length,unchangedWrites);
  assert.match(await page.locator('#availability-error').innerText(),/horaires.*incomplets/);
  // Persisted missions retain exact instants across the repeated hour in Zurich.
  const dst={window_start:'2026-10-25T00:30:00Z',window_end:'2026-10-25T01:30:00Z'};
  await open({persisted:true,window:dst});let before=writes.length;
  await page.locator('#mission-check-conditions').click();
  assert.equal(await page.locator('#availability-start').inputValue(),'2026-10-25T02:30');
  assert.equal(await page.locator('#availability-end').inputValue(),'2026-10-25T02:30');
  assert.equal(writes.length,before);
  await page.locator('#request-recommendation').click();await page.waitForFunction(()=>!state.requestingRecommendation);
  assert.deepEqual(writes[before].body.availability,{mode:'fixed_window',start:dst.window_start,end:dst.window_end});
  // An edited window follows the normal server-validated local-time contract.
  await open({persisted:true});before=writes.length;await page.locator('#mission-check-conditions').click();
  await page.locator('#availability-start').fill('2026-11-01T20:00');
  await page.locator('#availability-end').fill('2026-11-01T22:00');
  await page.locator('#request-recommendation').click();await page.waitForFunction(()=>!state.requestingRecommendation);
  assert.deepEqual(writes[before].body.availability,{mode:'fixed_window',start_local:'2026-11-01T20:00',end_local:'2026-11-01T22:00'});
  await open({missing:true});before=writes.length;await page.locator('#mission-check-conditions').click();
  assert.equal(writes.length,before);assert.equal(await page.evaluate(()=>state.view),'projects');
  await open();await page.locator('#mission-check-conditions').click();
  await page.evaluate(()=>prepareGuidedSession({projectId:'Sh2-129'}));
  assert.equal(await page.locator('#mission-recheck-summary').isVisible(),false);
  assert.equal(await page.locator('#request-recommendation').innerText(),'Préparer ma nuit');
  sessions=[{mission_id:'mission',execution:{execution_id:'exec',status:'in_progress'},evidence:[]}];
  await open();assert.equal(await page.locator('#mission-check-conditions').isDisabled(),true);sessions=[];
  await open();await page.evaluate(()=>{state.sessionBusy=true;updateMissionConditionsControl();});
  assert.equal(await page.locator('#mission-check-conditions').isDisabled(),true);
  await page.evaluate(()=>ui.mission.close());
  fail=true;await open();before=writes.length;await page.locator('#mission-check-conditions').click();await page.locator('#request-recommendation').click();await page.waitForFunction(()=>!state.requestingRecommendation);
  assert.equal(writes.length,before+1);assert.equal(await page.evaluate(()=>state.view),'availability');
  assert.deepEqual(await page.evaluate(()=>state.availability),{mode:'fixed_window',start,end});
  assert.deepEqual(await page.evaluate(()=>state.configuration.projects),config.projects);
  assert.deepEqual(errors,[]);
  assert(writes.every(w=>w.path==='/v1/tonight'),'no mission acceptance, session, evidence, credit, observation or configuration write');
  console.log('PASS: mission recheck, exact project/window, Simple/Pro × 4 sizes, persisted/past/site prefill, DST exact instants, edited dates, active-session guard, failure preservation, no domain writes beyond analysis.');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
