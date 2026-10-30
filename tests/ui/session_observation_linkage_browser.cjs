const {timeHeaders,timeData}=require('./timezone_fixture.cjs');
const {chromium}=require('playwright');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
(async()=>{
 const web=path.resolve(__dirname,'../../astropilot/web');
 const browser=await chromium.launch({headless:true,chromiumSandbox:true,
  ...(process.env.NIGHTMERIT_TEST_CHROME?{executablePath:process.env.NIGHTMERIT_TEST_CHROME}:{channel:'chrome'})});
 try{
  const context=await browser.newContext({timezoneId:'America/New_York'}),writes=[];let sessions=[],fail=false;
  await context.route('http://127.0.0.1:18461/**',async route=>{
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
  await page.goto('http://127.0.0.1:18461/');await page.waitForFunction(()=>state.view==='configuration_error');

  const results=[];
  for(const mode of ['simple','pro'])for(const width of [390,768,1280,1600]){
   await page.setViewportSize({width,height:900});
   async function setup(){
    await page.evaluate(mode=>{
     if(ui.observation.open)ui.observation.close();if(ui.mission.open)ui.mission.close();
     state.configuration={configured:true,site:{name:'SITE FICTIF',latitude:47,longitude:7,bortle:4,timezone:'Europe/Zurich'},projects:{},available_equipment:[],preset_equipment:[]};
     state.configurationDraft=draftFromConfiguration(state.configuration);
     state.decisionSiteReloadRequired=false;
     state.acceptedMission={mission_id:'mission',decision_id:'decision',acquisitionIntentId:'ou4_oiii',acceptedSiteGeneration:state.decisionSiteGeneration,acceptedSiteFingerprint:decisionSiteFingerprint(),mission:{night_date:'2026-10-30',target:'Ou4',site_timezone:'Europe/Zurich',selected_filter:{name:'OIII 6.5 nm'}}};
     state.currentDecision={decision_id:'decision',night_date:'2026-10-30'};
     state.currentDecisionSiteFingerprint=decisionSiteFingerprint();
     state.sessions=[{mission_id:'mission',execution:{execution_id:'session',status:'in_progress',actual_start:'2026-10-30T19:00:00Z'},evidence:[],credit:null}];
     state.activeSessionId='session';state.fieldObservationSelectedExecutionId=null;
     state.fieldObservationLock=null;state.fieldObservationDraftContext=null;state.fieldObservationAnchorContext=null;
     state.observationBusy=false;state.fieldObservationContextInvalid=false;
     state.sessionBusy=false;state.sessionWriteUncertain=false;
     applyUiMode(mode);setView('availability');renderSession();ui.mission.showModal();
    },mode);
   }
   async function capture(name,expected){
    const details=page.locator('#observation-temperature').locator('xpath=ancestor::details[1]');
    if(!(await details.evaluate(el=>el.open)))await details.locator('summary').click();
    await page.locator('#observation-temperature').fill('8');
    const result=await page.evaluate(()=>({label:document.querySelector('#observation-linkage').textContent,payload:fieldObservationDraftForContext(state.fieldObservationDraftContext)}));
    assert.equal(result.payload.execution_id,expected);
    if(expected)assert.match(result.label,/session de Ou4.*OIII.*démarrée le/);
    else assert.match(result.label,/Relevé météo indépendant/);
    assert.equal(await page.locator('#field-observation-dialog').evaluate(el=>el.scrollWidth<=el.clientWidth),true);
    results.push({mode,width,name,...result});
    if(process.argv[2]&&mode==='simple'&&width===1280){await page.locator('#observation-linkage').scrollIntoViewIfNeeded();await page.screenshot({path:path.join(process.argv[2],name+'.png')});}
    await page.evaluate(()=>ui.observation.close());
   }
   await setup();
   assert.equal(await page.locator('#session-choice').inputValue(),'session');
   await page.locator('#add-field-observation-mission').click();
   await capture('depuis-session-affichee','session');
   // Selecting the already displayed option is not a new choice event.
   await page.locator('#session-choice').selectOption('');
   await page.locator('#session-choice').selectOption('session');
   await page.locator('#add-field-observation-mission').click();
   await capture('apres-selection-explicite','session');
   await page.evaluate(()=>ui.mission.close());
   await page.evaluate(()=>{show('decision');ui.addObservationDecision.hidden=false;});
   await page.locator('#add-field-observation-decision').click();
   await capture('depuis-ecran-general',null);
  }
  // No chosen session must stay independent even if the mission has sessions.
  await page.evaluate(()=>{state.activeSessionId=null;state.fieldObservationSelectedExecutionId='session';ui.mission.showModal();});
  await page.locator('#add-field-observation-mission').click();
  assert.equal(await page.evaluate(()=>state.fieldObservationDraftContext.execution_id),null);
  assert.match(await page.locator('#observation-linkage').innerText(),/indépendant/);
  await page.evaluate(()=>{ui.observation.close();state.activeSessionId='session';});
  // A session from another mission or an uncertain session must not be bound.
  await page.evaluate(()=>{
    if(ui.mission.open)ui.mission.close();
    state.sessions[0].mission_id='different-mission';ui.mission.showModal();
  });
  await page.locator('#add-field-observation-mission').click();
  assert.equal(await page.locator('#field-observation-dialog').isVisible(),false);
  assert.match(await page.locator('#session-status').innerText(),/ne correspond plus/);
  await page.evaluate(()=>{state.sessions[0].mission_id='mission';state.sessions[0].execution.status='unconfirmed';});
  await page.locator('#add-field-observation-mission').click();
  assert.equal(await page.locator('#field-observation-dialog').isVisible(),false);
  assert.match(await page.locator('#session-status').innerText(),/Vérifiez l’état/);
  assert.deepEqual(writes,[],'no writes, real or fictive');assert.deepEqual(errors,[]);
  if(process.argv[2])fs.writeFileSync(path.join(process.argv[2],'resultats.json'),JSON.stringify(results,null,2));
  console.log('PASS: 24 scénarios Simple/Pro 390/768/1280/1600 : lien depuis session affichée et sélection explicite, identité visible, écran général indépendant, absence de session choisie et deux protections de contexte. Aucun POST.');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
