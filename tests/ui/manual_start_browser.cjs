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
 let sessions=[];
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
    return response(route,sessions[0].execution);
   }
   assert.equal(u.pathname,'/v1/execution-transitions','No credit or other write allowed');
   assert.equal(body.execution_id,sessions[0].execution.execution_id);assert.equal(body.status,'in_progress');
   sessions[0].execution={...body};return response(route,body);
  }
  if(u.pathname==='/ui/timezone-data.js')return route.fulfill({headers:timeHeaders,contentType:'text/javascript',body:timeData});
  const file=u.pathname==='/'?'index.html':u.pathname.startsWith('/ui/')?u.pathname.slice(4):null;
  if(file&&path.basename(file)===file&&fs.existsSync(path.join(web,file)))return route.fulfill({headers:timeHeaders,contentType:file.endsWith('.js')?'text/javascript':file.endsWith('.css')?'text/css':'text/html',body:fs.readFileSync(path.join(web,file))});
  if(u.pathname==='/v1/configuration')return response(route,{},503);
  if(u.pathname==='/v1/analysis-history/decision-fictitious')return response(route,{decision_id:mission.decision_id,result:{}});
  if(u.pathname===`/v1/missions/${mission.mission_id}/executions`)return response(route,sessions);
  if(u.pathname.endsWith('/guardian-renewal'))return response(route,{schema_version:'guardian-explicit-renewal-v1',execution_id:sessions[0]?.execution.execution_id,guardian_mode_enabled:false,server_time:new Date().toISOString(),renewal_eligible:false});
  if(u.pathname.startsWith('/v1/executions/')&&u.pathname.endsWith('/session'))return response(route,{},404);
  if(u.pathname==='/v1/demo-context')return response(route,{enabled:false,weather:'real'});
  assert.notEqual(u.pathname,'/v1/tonight','No weather analysis allowed');
  return response(route,{},503);
 });
 await page.goto(origin);await page.waitForFunction(()=>state.view==='configuration_error');
 const writes=()=>requests.filter(r=>r.method!=='GET');
 for(const width of [390,1280])for(const action of ['cancel','escape','recheck','confirm','changed-context']){
  sessions=[];await page.setViewportSize({width,height:1000});
  await page.evaluate(({config,accepted})=>{
   if(document.querySelector('#manual-start-dialog').open)closeManualStart();if(ui.mission.open)ui.mission.close();
   state.configuration=structuredClone(config);state.configurationDraft=draftFromConfiguration(state.configuration);state.configurationGeneration=1;state.decisionSiteGeneration=1;state.decisionSiteReloadRequired=false;state.selectedProjectId='Rosette';state.sessionBusy=false;state.sessionWriteUncertain=false;state.pendingAcceptanceAttempt=null;state.acceptanceBlocked=false;state.requestingRecommendation=false;guardianUI.pending=false;
   setView('availability');state.acceptedMission=structuredClone(accepted);state.savedMissions=[structuredClone(accepted)];state.missionWeatherChecks={};state.missionWeatherOrigins={};renderMission(accepted.mission);ui.mission.showModal();
  },{config,accepted});
  await page.waitForFunction(()=>state.missionConditionsReady);
  if(action==='confirm')await page.evaluate(()=>{
   const accepted=state.acceptedMission,context={accepted,siteFingerprint:decisionSiteFingerprint()};
   saveMissionWeatherCheck(context,{status:'weather_refused',catalog_key:'Rosette',weather_decision:{presentation:{summary:'Nuages fictifs : refus conservé.'}}});
   saveMissionWeatherCheck(context,null);
  });
  const before=await page.evaluate(()=>JSON.stringify({projects:state.configuration.projects,missions:state.savedMissions,accepted:state.acceptedMission}));
  const start=writes().length;
  await page.locator('#session-start').click();
  const dialog=page.locator('#manual-start-dialog');await dialog.waitFor({state:'visible'});
  assert.equal(await page.locator('#manual-start-cancel').evaluate(e=>e===document.activeElement),true);
  assert.equal(writes().length,start);assert.equal(sessions.length,0);
  assert.match(await dialog.innerText(),/ne commande pas votre matériel/);
  if(action==='confirm')assert.match(await dialog.innerText(),/Nuages fictifs.*Ce refus n’a pas été réévalué/s);
  await page.screenshot({path:path.join(proof,`dialog-${action}-${width}.png`),fullPage:true});
  if(action==='cancel')await page.locator('#manual-start-cancel').click();
  else if(action==='escape')await page.keyboard.press('Escape');
  else if(action==='recheck')await page.locator('#manual-start-recheck').click();
  else {
   if(action==='changed-context')await page.evaluate(()=>state.decisionSiteGeneration++);
   await page.locator('#manual-start-confirm').click();
   await page.waitForFunction(()=>!state.sessionBusy);
  }
  await dialog.waitFor({state:'hidden'});
  if(action==='confirm'){
   assert.deepEqual(writes().slice(start).map(r=>r.path),['/v1/executions','/v1/execution-transitions']);
   assert.equal(sessions.length,1);assert.equal(sessions[0].execution.status,'in_progress');assert.equal(sessions[0].credit,null);
   assert.match(await page.locator('#session-status').innerText(),/Début de séance déclaré.*Aucun temps de pose ajouté/s);
   assert.equal(await page.evaluate(()=>state.missionWeatherChecks['manual-fictitious'].status),'unknown');
  }else{
   assert.equal(writes().length,start);assert.equal(sessions.length,0);
   if(action==='recheck'){
    assert.equal(await page.evaluate(()=>state.view),'availability');
    assert.equal(await page.locator('#availability-preparation-minutes').inputValue(),'20');
    assert.equal(await page.locator('#availability-flats-minutes').inputValue(),'5');
    assert.equal(await page.evaluate(()=>state.missionRecheck.accepted.mission_id),mission.mission_id);
   }
  }
  assert.equal(await page.evaluate(()=>JSON.stringify({projects:state.configuration.projects,missions:state.savedMissions,accepted:state.acceptedMission})),before);
  results.push({width,action,pass:true,writes:writes().length-start,no_credit:true,counters:{OIII_minutes:40,SII_minutes:25}});
 }
 assert.deepEqual(errors,[]);
 fs.writeFileSync(path.join(proof,'verification.json'),JSON.stringify({success:true,results,errors,requests,network:'all requests intercepted on fictional origin; no analysis request permitted',limitation:'real UI against fictitious services, not compiled kit or real backend'},null,2));
 console.log('PASS: '+results.length+' parcours fictifs, zéro collecte, zéro crédit.');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1});
