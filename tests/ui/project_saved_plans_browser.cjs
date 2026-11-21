// Fictitious profiles and intercepted HTTP only; no live instance or weather provider.
const {chromium}=require('playwright');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {timeHeaders,timeData}=require('./timezone_fixture.cjs');
const origin='https://nightmerit.test';
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.NIGHTMERIT_TEST_CHROME,args:['--use-mock-keychain']});
 try {
  const page=await browser.newPage({timezoneId:'Europe/Zurich'}),errors=[],writes=[],reads=[],cases=[];
  const web=path.resolve(__dirname,'../../astropilot/web'),out=process.env.NIGHTMERIT_PROOF_DIR;
  let failHistory=false,failSessions=false,deferred=null;
  const mission=(id,key,filter,start)=>({mission_id:id,selection_id:'s-'+id,decision_id:'d-'+id,target:key,
   window_start:start,window_end:start.replace('20:00','22:00'),setup_steps:[],tasks:[],selected_filter:{filter_type:filter},
   recommendation_confidence:0.8,equipment_summary:[]});
  const plans=[['m42','M42','Ha','2026-11-21T20:00:00+01:00'],['r1','Rosette','OIII','2026-11-22T20:00:00+01:00'],['r2','Rosette','SII','2026-11-23T20:00:00+01:00']]
   .map(([id,key,filter,start])=>({status:'accepted',catalog_key:key,mission_id:id,selection_id:'s-'+id,decision_id:'d-'+id,mission:mission(id,key,filter,start)}));
  const config={configured:true,profile_revision:1,site:{name:'TEST FICTIF',latitude:46.88812,longitude:6.55137,bortle:4,timezone:'Europe/Zurich'},equipment:{preset_id:'samyang_183'},projects:{M42:{},Rosette:{},M31:{}}};
  const progress=key=>({project_id:key,profile_revision:1,acquisition_intents:[{acquisition_intent_id:key+'_ha',filter_type:'Ha'}],acquisition_intent_targets:[{acquisition_intent_id:key+'_ha',target_hours:2}],intent_progress_breakdown:[{acquisition_intent_id:key+'_ha',effective_total_seconds:2400}],acquisition_intent_progress:[]});
  page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/*',async route=>{
   const req=route.request(),url=new URL(req.url());assert.equal(url.origin,origin,'No external requests allowed');
   if(req.method()!=='GET'){writes.push(req.url());return route.abort();}
   if(url.pathname==='/ui/timezone-data.js')return route.fulfill({headers:timeHeaders,contentType:'text/javascript',body:timeData});
   const filename=url.pathname==='/'?'index.html':url.pathname.startsWith('/ui/')?url.pathname.slice(4):null;
   if(filename&&path.basename(filename)===filename&&fs.existsSync(path.join(web,filename)))return route.fulfill({headers:timeHeaders,contentType:filename.endsWith('.js')?'text/javascript':filename.endsWith('.css')?'text/css':'text/html',body:fs.readFileSync(path.join(web,filename))});
   reads.push(url.pathname);
   const json=(data,status=200)=>route.fulfill({headers:timeHeaders,status,json:data});
   if(url.pathname==='/v1/accepted-mission/current')return json(plans[0]);
   if(url.pathname==='/v1/accepted-missions'){
    if(deferred){const wait=deferred;deferred=null;await wait;}
    return json(failHistory?{}:plans,failHistory?503:200);
   }
   if(url.pathname==='/v1/execution-sessions')return json(failSessions?{}:[],failSessions?503:200);
   const match=url.pathname.match(/^\/v1\/projects\/([^/]+)\/progress$/);
   if(match)return json(progress(decodeURIComponent(match[1])));
   return json({},503);
  });
  await page.goto(origin);await page.waitForFunction(()=>typeof state!=='undefined'&&state.view==='configuration_error');
  async function setup(mode){
   await page.evaluate(({config,mode})=>{
    applyUiMode(mode);state.configuration=structuredClone(config);state.configurationDraft=draftFromConfiguration(state.configuration);
    state.savedMissionProjectId=null;state.savedMissionHistoryUnavailable=false;state.savedMissionLoading=false;state.acceptedMission=null;
    state.progressEditor=null;state.selectedProjectId=null;state.pendingAcceptanceAttempt=null;state.acceptanceBlocked=false;
    state.configurationGeneration=(state.configurationGeneration||0)+1;
    setView('projects');renderSimpleProjects(Object.entries(state.configuration.projects));
   },{config,mode});
   await page.evaluate(()=>restoreSavedMission());
  }
  const card=key=>page.locator('.simple-project-card').filter({has:page.getByRole('heading',{name:key==='Rosette'?'Rosette':'M42',exact:true})});
  for(const mode of ['simple','pro'])for(const width of [390,1280]){
   await page.setViewportSize({width,height:900});await setup(mode);
   // Only Beginner exposes the simple project cards; Advanced uses the same chooser below.
   if(mode==='simple'){
    const more=card('Rosette').locator('details');await more.locator('summary').click();
    await card('Rosette').getByRole('button',{name:'Retrouver les plans de ce projet',exact:true}).click();
   }else await page.evaluate(()=>openProjectSavedMissions('Rosette'));
   await page.locator('#saved-mission-choice').waitFor({state:'visible'});
   assert.deepEqual(await page.locator('#saved-mission-choice option').evaluateAll(es=>es.map(e=>e.value)),['r1','r2']);
   assert.equal(await page.locator('#saved-mission-choice').inputValue(),'r1');
   await page.waitForFunction(()=>document.activeElement===document.querySelector('#saved-mission-choice'));
   assert.match(await page.locator('#saved-mission-heading').innerText(),/Rosette/);
   const labels=await page.locator('#saved-mission-choice option').allTextContents();assert.match(labels[0],/OIII/);assert.match(labels[1],/SII/);
   await page.locator('#saved-mission-choice').selectOption('r2');await page.locator('#open-saved-mission').click();
   assert.equal(await page.evaluate(()=>state.acceptedMission.mission_id),'r2');assert.equal(await page.locator('#mission-dialog').evaluate(el=>el.open),true);
   await page.locator('#close-mission').click();
   if(out){fs.mkdirSync(out,{recursive:true});await page.locator('#saved-mission-entry').screenshot({path:path.join(out,`plans-${mode}-${width}.png`)});}
   // A history retry is a read, not a new choice of active mission.
   const active=await page.evaluate(()=>JSON.stringify(state.acceptedMission));
   failHistory=true;await page.evaluate(()=>restoreSavedMission({preserveActiveMission:true}));
   assert.equal(await page.evaluate(()=>JSON.stringify(state.acceptedMission)),active);
   assert.deepEqual(await page.locator('#saved-mission-choice option').evaluateAll(es=>es.map(e=>e.value).sort()),['r1','r2']);
   assert.match(await page.locator('#saved-mission-history-status').innerText(),/incomplète/);
   failHistory=false;await page.locator('#saved-mission-retry').click();await page.waitForFunction(()=>!state.savedMissionLoading);
   assert.equal(await page.evaluate(()=>JSON.stringify(state.acceptedMission)),active);
   // Preparing a different project must also update an already scoped list.
   await page.evaluate(()=>prepareGuidedSession({projectId:'M42'}));
   assert.match(await page.locator('#saved-mission-heading').innerText(),/M42/);
   assert.deepEqual(await page.locator('#saved-mission-choice option').evaluateAll(es=>es.map(e=>e.value)),['m42']);
   await page.evaluate(()=>openProjectSavedMissions('Rosette'));
   await page.locator('#saved-mission-all').click();assert.equal(await page.locator('#saved-mission-choice option').count(),3);
   // Empty profile/project must never reuse the globally current M42 mission.
   await page.evaluate(()=>openProjectSavedMissions('M31'));
   assert.equal(await page.locator('#saved-mission-choice option').count(),0);assert.equal(await page.locator('#open-saved-mission').isDisabled(),true);
   assert.equal(await page.locator('#saved-mission-history-status').innerText(),'Aucun plan enregistré pour ce projet.');
   assert.equal(await page.locator('#saved-mission-prepare').isVisible(),true);
   await page.locator('#saved-mission-prepare').click();assert.equal(await page.evaluate(()=>state.selectedProjectId),'M31');
   failHistory=true;await page.evaluate(()=>restoreSavedMission());
   assert.match(await page.locator('#saved-mission-history-status').innerText(),/incomplète/);assert.equal(await page.locator('#saved-mission-prepare').isVisible(),false);
   failHistory=false;await page.locator('#saved-mission-retry').click();await page.waitForFunction(()=>!state.savedMissionLoading);
   assert.equal(await page.locator('#saved-mission-history-status').innerText(),'Aucun plan enregistré pour ce projet.');
   failSessions=true;await page.evaluate(()=>restoreSavedMission());assert.match(await page.locator('#saved-mission-history-status').innerText(),/incomplète/);
   failSessions=false;await page.locator('#saved-mission-retry').click();await page.waitForFunction(()=>!state.savedMissionLoading);
   // Late history response must not restore the previous project's chooser.
   let release;deferred=new Promise(r=>release=r);
   await page.evaluate(()=>{void restoreSavedMission()});await page.waitForFunction(()=>state.savedMissionLoading);
   await page.evaluate(()=>openProjectSavedMissions('Rosette'));release();await page.waitForFunction(()=>!state.savedMissionLoading);
   assert.deepEqual(await page.locator('#saved-mission-choice option').evaluateAll(es=>es.map(e=>e.value)),['r1','r2']);
   const bounds=await page.locator('#saved-mission-entry').evaluate(el=>({left:el.getBoundingClientRect().left,right:el.getBoundingClientRect().right,overflow:el.scrollWidth>el.clientWidth}));
   assert.ok(bounds.left>=0&&bounds.right<=width&&!bounds.overflow,JSON.stringify(bounds));
   assert.deepEqual(await page.evaluate(()=>state.configuration),config);cases.push({mode,width,labels,bounds});
  }
  assert.deepEqual(errors,[]);assert.deepEqual(writes,[]);
  if(out)fs.writeFileSync(path.join(out,'verification.json'),JSON.stringify({success:true,cases,writes,reads,errors,profiles_fictitious:true,weather_calls:reads.filter(p=>p.includes('tonight')||p.includes('suggestions')).length},null,2));
  console.log('PASS: project plan chooser, selected project, empty/partial history, retry, late read, keyboard focus, mobile and Advanced; no writes or weather');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1});
