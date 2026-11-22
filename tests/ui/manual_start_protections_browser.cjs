// Real UI, isolated browser, fictitious HTTP services only. No weather collection.
const {chromium}=require('playwright');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {timeHeaders,timeData}=require('./timezone_fixture.cjs');
const origin='https://nightmerit.test';
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.NIGHTMERIT_TEST_CHROME,args:['--use-mock-keychain']});
 const proof=process.env.NIGHTMERIT_PROOF_DIR;fs.mkdirSync(proof,{recursive:true});
 const results=[],errors=[],requests=[];
 try {
 const page=await browser.newPage({timezoneId:'Europe/Zurich',serviceWorkers:'block'});
 page.on('pageerror',e=>errors.push(e.message));
 const web=path.resolve(__dirname,'../../astropilot/web');
 const config={configured:true,profile_revision:1,site:{name:'Buttes fictif',latitude:46.88812,longitude:6.55137,bortle:4,timezone:'Europe/Zurich'},active_equipment_id:'fictional',available_equipment:[],preset_equipment:[],projects:{Rosette:{hours:65/60,target_hours:3,oiii_minutes:40,sii_minutes:25}}};
 const mission={mission_id:'manual-fictitious',selection_id:'selection-fictitious',decision_id:'decision-fictitious',target:'Rosette',site_name:'Buttes fictif',site_timezone:'Europe/Zurich',window_start:'2026-11-23T20:20:00+01:00',window_end:'2026-11-23T21:55:00+01:00',recommended_hours:95/60,acquisition_intent_id:'rosette_sii',selected_filter:{name:'SII fictif',filter_type:'SII'},equipment:[],tasks:[{title:'Préparation',start:'T−20 min',end:'T'},{title:'Flats',start:'Fin',end:'Fin+5 min'}]};
 const accepted={mission_id:mission.mission_id,selection_id:mission.selection_id,decision_id:mission.decision_id,selectedCatalogKey:'Rosette',acquisitionIntentId:'rosette_sii',source:'persisted',mission,windowTimezone:'Europe/Zurich'};
 let sessions=[],scenario=null,lossDelivered=false,lookupGate=null,releaseLookup=null,lookupReached=null,markLookupReached=null;
 const response=(route,data,status=200)=>route.fulfill({status,headers:timeHeaders,json:data});
 await page.route('**/*',async route=>{
  const req=route.request(),u=new URL(req.url());
  assert.equal(u.origin,origin,'No access outside fixture origin');
  requests.push({method:req.method(),path:u.pathname});
  if(req.method()!=='GET') {
   const body=req.postDataJSON();assert.equal(req.method(),'POST');
   if(u.pathname==='/v1/executions') {
    assert.equal(body.mission_id,mission.mission_id);assert.equal(sessions.length,0);
    sessions=[{mission_id:mission.mission_id,mission,project_id:'Rosette',acquisition_intent_id:'rosette_sii',execution:{execution_id:body.execution_id,mission_id:mission.mission_id,status:'not_started',actual_start:null},evidence:[],credit:null,historical_baseline_seconds:1500,historical_baseline_confirmed:true,current_acquired_seconds:1500,acquired_before_seconds:1500,acquired_after_seconds:1500,session_credit_seconds:0,target_hours:3,remaining_hours:155/60,profile_revision:1}];
    if(scenario==='lost-create'&&!lossDelivered){lossDelivered=true;return route.abort('failed');}
    return response(route,sessions[0].execution);
   }
   assert.equal(u.pathname,'/v1/execution-transitions','No credit or other write allowed');
   assert.equal(body.execution_id,sessions[0].execution.execution_id);assert.equal(body.status,'in_progress');
   if(scenario==='guardian-refusal'){
    assert(req.headers()['idempotency-key']);assert.equal(req.headers()['x-guardian-owner-instance-id'],'fixture-owner');
    return response(route,{code:'guardian_session_not_owned',execution_commit:'not_attempted',guardian_publication:'not_attempted'},409);
   }
   sessions[0].execution={...body};
   if(scenario==='lost-transition'&&!lossDelivered){lossDelivered=true;return route.abort('failed');}
   return response(route,body);
  }
  if(u.pathname==='/ui/timezone-data.js')return route.fulfill({headers:timeHeaders,contentType:'text/javascript',body:timeData});
  const file=u.pathname==='/'?'index.html':u.pathname.startsWith('/ui/')?u.pathname.slice(4):null;
  if(file&&path.basename(file)===file&&fs.existsSync(path.join(web,file)))return route.fulfill({headers:timeHeaders,contentType:file.endsWith('.js')?'text/javascript':file.endsWith('.css')?'text/css':'text/html',body:fs.readFileSync(path.join(web,file))});
  if(u.pathname==='/v1/configuration')return response(route,{},503);
  if(u.pathname==='/v1/analysis-history/decision-fictitious')return response(route,{decision_id:mission.decision_id,result:{}});
  if(u.pathname===`/v1/missions/${mission.mission_id}/executions`)return response(route,sessions);
  if(u.pathname.endsWith('/guardian-renewal'))return response(route,{schema_version:'guardian-explicit-renewal-v1',execution_id:sessions[0]?.execution.execution_id,guardian_mode_enabled:scenario==='guardian-refusal',owner_instance_id:'fixture-owner',server_time:new Date().toISOString(),renewal_eligible:false});
  if(u.pathname.startsWith('/v1/executions/')&&u.pathname.endsWith('/session')){
   if(scenario==='changed-context-pending'&&lookupGate){const gate=lookupGate;lookupGate=null;markLookupReached();await gate;}
   const id=decodeURIComponent(u.pathname.split('/')[3]);
   const session=sessions.find(s=>s.execution.execution_id===id);
   return response(route,session||{},session?200:404);
  }
  if(u.pathname==='/v1/demo-context')return response(route,{enabled:false,weather:'real'});
  assert.notEqual(u.pathname,'/v1/tonight','No weather analysis allowed');
  return response(route,{},503);
 });
 await page.goto(origin);await page.waitForFunction(()=>state.view==='configuration_error');
 const writes=()=>requests.filter(r=>r.method!=='GET');
 for(const width of [390,1280])for(const action of ['double-click','lost-create','lost-transition','changed-context-pending','guardian-refusal','favorable']){
  sessions=[];scenario=action;lossDelivered=false;lookupGate=null;releaseLookup=null;
  if(action==='changed-context-pending'){
   lookupGate=new Promise(resolve=>{releaseLookup=resolve;});
   lookupReached=new Promise(resolve=>{markLookupReached=resolve;});
  }
  await page.setViewportSize({width,height:1000});
  await page.evaluate(({config,accepted})=>{
   if(document.querySelector('#manual-start-dialog').open)closeManualStart();if(ui.mission.open)ui.mission.close();
   state.configuration=structuredClone(config);state.configurationDraft=draftFromConfiguration(state.configuration);state.configurationGeneration=1;state.decisionSiteGeneration=1;state.decisionSiteReloadRequired=false;state.selectedProjectId='Rosette';state.sessionBusy=false;state.sessionWriteUncertain=false;state.pendingAcceptanceAttempt=null;state.acceptanceBlocked=false;state.requestingRecommendation=false;guardianUI.pending=false;
   localStorage.clear();guardianUI.status=null;guardianUI.displayStatus=null;
   setView('availability');state.acceptedMission=structuredClone(accepted);state.savedMissions=[structuredClone(accepted)];state.missionWeatherChecks={};state.missionWeatherOrigins={};renderMission(accepted.mission);ui.mission.showModal();
  },{config,accepted});
  await page.waitForFunction(()=>state.missionConditionsReady);
  if(action==='favorable')await page.evaluate(()=>{
   // Synthetic forecast with a production provider name to exercise that branch.
   // This is not real Open-Meteo data and causes no provider request.
   const accepted=state.acceptedMission;
   saveMissionWeatherCheck({accepted,siteFingerprint:decisionSiteFingerprint()}, {
    status:'available',catalog_key:'Rosette',selected_acquisition_intent_id:'rosette_sii',
    selected_filter:{filter_type:'SII'},window_start:accepted.mission.window_start,window_end:accepted.mission.window_end,
    weather_trust:{provider:'Open-Meteo',retrieved_at_utc:new Date().toISOString(),freshness_status:'fresh',validation_status:'validated',snapshot_age_minutes:0,maximum_age_minutes:90,valid_from:'2026-11-22T00:00:00Z',valid_until:'2026-11-24T00:00:00Z'},
    weather_decision:{admissibility:'admissible'}});
  });
  const before=await page.evaluate(()=>JSON.stringify({projects:state.configuration.projects,missions:state.savedMissions,accepted:state.acceptedMission}));
  const start=writes().length;
  await page.locator('#session-start').click();
  const dialog=page.locator('#manual-start-dialog');
  if(action==='favorable')assert.equal(await dialog.isVisible(),false);
  else {
   await dialog.waitFor({state:'visible'});assert.equal(writes().length,start);
   if(action==='double-click')await page.locator('#manual-start-confirm').evaluate(button=>{button.click();button.click();});
   else await page.locator('#manual-start-confirm').click();
  }
  if(action==='changed-context-pending'){
   let timeout;
   try { await Promise.race([lookupReached,new Promise((_,reject)=>{timeout=setTimeout(()=>reject(new Error('Lookup was not reached before context change')),5000);})]); }
   finally { clearTimeout(timeout); }
   assert.equal(await page.evaluate(()=>state.sessionBusy),true);
   await page.evaluate(()=>state.decisionSiteGeneration++);
   releaseLookup();
  }
  await page.waitForFunction(()=>!state.sessionBusy);
  await dialog.waitFor({state:'hidden'});
  let added=writes().slice(start);
  if(action==='changed-context-pending'){
   assert.equal(added.length,0);assert.equal(sessions.length,0);
   assert.match(await page.locator('#session-status').innerText(),/contexte.*changé/s);
  }else if(action==='guardian-refusal'){
   assert.deepEqual(added.map(r=>r.path),['/v1/executions','/v1/execution-transitions']);
   assert.equal(sessions.length,1);assert.equal(sessions[0].execution.status,'not_started');
   assert.match(await page.locator('#session-status').innerText(),/transition non enregistrée/);
   assert.doesNotMatch(await page.locator('#session-status').innerText(),/Début de séance déclaré/);
  }else if(action==='lost-create'){
   assert.deepEqual(added.map(r=>r.path),['/v1/executions']);
   assert.equal(sessions.length,1);assert.equal(sessions[0].execution.status,'not_started');
   assert.match(await page.locator('#session-status').innerText(),/réponse incertaine/);
   await page.locator('#session-start').click();await dialog.waitFor({state:'visible'});
   await page.locator('#manual-start-confirm').click();await page.waitForFunction(()=>!state.sessionBusy);
   added=writes().slice(start);
   assert.deepEqual(added.map(r=>r.path),['/v1/executions','/v1/execution-transitions']);
   assert.equal(sessions.length,1);assert.equal(sessions[0].execution.status,'in_progress');
  }else{
   assert.deepEqual(added.map(r=>r.path),['/v1/executions','/v1/execution-transitions']);
   assert.equal(sessions.length,1);assert.equal(sessions[0].execution.status,'in_progress');
   if(action==='lost-transition'){
    assert.match(await page.locator('#session-status').innerText(),/réponse incertaine/);
    const count=writes().length;await page.evaluate(()=>requestManualStart());
    assert.equal(writes().length,count);assert.equal(await dialog.isVisible(),false);
   }
  }
  assert(sessions.every(s=>!s.credit&&s.session_credit_seconds===0));
  await page.screenshot({path:path.join(proof,`result-${action}-${width}.png`),fullPage:true});
  assert.equal(await page.evaluate(()=>JSON.stringify({projects:state.configuration.projects,missions:state.savedMissions,accepted:state.acceptedMission})),before);
  results.push({width,action,pass:true,writes:writes().length-start,no_credit:true,counters:{OIII_minutes:40,SII_minutes:25}});
 }
 assert.deepEqual(errors,[]);
 fs.writeFileSync(path.join(proof,'verification.json'),JSON.stringify({success:true,results,errors,requests,network:'all requests intercepted on fictional origin; no analysis request permitted',limitation:'real UI against fictitious services, not compiled kit or real backend'},null,2));
 console.log('PASS: '+results.length+' protections fictives, zéro collecte, zéro crédit.');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1});
