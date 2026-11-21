// Only fictitious profile data and intercepted HTTP. Never uses an open instance.
const {chromium}=require('playwright');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {timeHeaders,timeData}=require('./timezone_fixture.cjs');
const origin='https://nightmerit.test';
const row=(id,type,h)=>({acquisition_intent_id:id,filter_type:type,target_hours:3,acquired_hours:h,remaining_hours:3-h,status:'to_complete'});
const base={status:'available',decision_id:'summary-fictitious',catalog_key:'Rosette',target:'Rosette',target_decision_status:'recommended',action:'continue_project',night_date:'2026-11-21',
 selected_acquisition_intent_id:'r_oiii',acquisition_intent_selection_status:'selected',viable_acquisition_intent_ids:['r_oiii'],acquisition_intent_options:[{acquisition_intent_id:'r_oiii',label:'OIII'}],
 selected_filter:{name:'Filtre OIII fictif',filter_type:'OIII'},window_start:'2026-11-21T21:00:00+01:00',window_end:'2026-11-21T23:00:00+01:00',recommended_hours:1.5,
 astro_quality:{score:78,decision_score:78,decision_eligible:true,label:'good'},recommendation_confidence:.8,
 explanation:{positives:[{title:'Cible bien placée',value:'Altitude favorable sur le créneau'}],information:[],warnings:[{title:'Passages nuageux possibles',value:'À surveiller sur place'}]},
 weather_trust:{provider:'fixture-only',validation_status:'validated',freshness_status:'fresh',timezone:'Europe/Zurich',retrieved_at_utc:'2026-11-21T18:00:00Z',valid_from:'2026-11-21T18:00:00Z',valid_until:'2026-11-22T06:00:00Z'},
 weather_decision:{admissibility:'admissible',presentation:{label:'Conditions fictives',summary:'Jeu de données synthétique'}},
 project_comparison:[{project_id:'M42',filters:[row('m_oiii','OIII',1)]},{project_id:'Rosette',filters:[row('r_oiii','OIII',40/60),row('r_sii','SII',25/60)]}]};
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.NIGHTMERIT_TEST_CHROME,args:['--use-mock-keychain']});
 try {
  const page=await browser.newPage({timezoneId:'Europe/Zurich'}),errors=[],writes=[],cases=[];
  const web=path.resolve(__dirname,'../../astropilot/web'),out=process.env.NIGHTMERIT_PROOF_DIR;
  let response=structuredClone(base),accepted=false;
  page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/*',async route=>{
   const request=route.request(),url=new URL(request.url());assert.equal(url.origin,origin);
   const json=(data,status=200)=>route.fulfill({headers:timeHeaders,status,json:data});
   if(request.method()!=='GET'){
    writes.push({path:url.pathname,body:request.postDataJSON()});
    if(url.pathname==='/v1/tonight'){
     assert.equal(request.postDataJSON().compare_projects,true);return json(response);
    }
    assert.equal(url.pathname,'/v1/decision-selections');assert.equal(request.postDataJSON().acquisition_intent_id,'r_sii');accepted=true;
    return json({status:'accepted',catalog_key:'Rosette',decision_id:base.decision_id,selection_id:'selection-fictitious',mission_id:'mission-fictitious',selected_acquisition_intent_id:'r_sii',
     mission:{mission_id:'mission-fictitious',selection_id:'selection-fictitious',decision_id:base.decision_id,target:'Rosette',acquisition_intent_id:'r_sii',site_timezone:'Europe/Zurich',selected_filter:{name:'Filtre SII fictif',filter_type:'SII'},window_start:'2026-11-21T22:00:00+01:00',window_end:'2026-11-21T23:00:00+01:00',recommended_hours:1,expected_gain:1,setup_steps:[],tasks:[],equipment_summary:[],reasons:[{title:'Créneau confirmé',value:'Valeur de la mission',severity:'info'},{title:'Rosée à surveiller',value:'Contrôle sur place',severity:'warning'}]}});
   }
   if(url.pathname==='/ui/timezone-data.js')return route.fulfill({headers:timeHeaders,contentType:'text/javascript',body:timeData});
   const file=url.pathname==='/'?'index.html':url.pathname.startsWith('/ui/')?url.pathname.slice(4):null;
   if(file&&path.basename(file)===file&&fs.existsSync(path.join(web,file)))return route.fulfill({headers:timeHeaders,contentType:file.endsWith('.js')?'text/javascript':file.endsWith('.css')?'text/css':'text/html',body:fs.readFileSync(path.join(web,file))});
   if(url.pathname==='/v1/demo-context')return json({enabled:false,weather:'real'});
   if(url.pathname==='/v1/execution-sessions')return json([]);
   return json({},503);
  });
  await page.goto(origin);await page.waitForFunction(()=>state.view==='configuration_error');
  const config={configured:true,profile_revision:1,site:{name:'PROFIL FICTIF',latitude:46.88812,longitude:6.55137,bortle:4,timezone:'Europe/Zurich'},equipment:{preset_id:'samyang_183'},projects:{Rosette:{hours:0},M42:{hours:0}}};
  const summary=page.locator('.project-tonight-summary');
  const snapshot=()=>page.evaluate(()=>({state:JSON.stringify(state),score:document.querySelector('#quality-score').textContent,target:document.querySelector('#target-name').textContent,window:document.querySelector('#window-value').textContent,duration:document.querySelector('#duration-value').textContent,filter:document.querySelector('#filter-value').textContent,actionDisabled:document.querySelector('#open-mission').disabled}));

  const remaining=()=>structuredClone(base.project_comparison);
  const complete={...structuredClone(base),status:'no_candidate',project_comparison:remaining().map(p=>({...p,filters:p.filters.map(f=>({...f,status:'completed',remaining_hours:0,acquired_hours:f.target_hours}))}))};
  const missing={...structuredClone(complete),project_comparison:[{project_id:'Rosette',filters:[{filter_type:'SII',status:'incomplete_data',target_hours:3,acquired_hours:null,remaining_hours:null}]}]};
  const mixed={...structuredClone(complete),project_comparison:[{project_id:'Rosette',filters:[complete.project_comparison[1].filters[0],missing.project_comparison[0].filters[0]]}]};
  const weather={...structuredClone(base),status:'weather_refused',weather_decision:{admissibility:'refused',presentation:{label:'Météo défavorable fictive',summary:'Refus explicite de cette analyse'}}};
  const short={...structuredClone(base),status:'no_productive_window',actionability_refusal:{conclusion:'no_productive_window',status:'constraints_refusal',refusal_stage:'continuous_window_too_short',best_productive_window_minutes:35,required_continuous_minutes:60}};
  const equipment={...structuredClone(base),status:'no_mission',creation_refusal:'no_eligible_acquisition_intent',acquisition_intent_assessments:[{status:'not_eligible',label:'OIII',reason_codes:['required_filter_unavailable']}]};
  const unknown={...structuredClone(base),status:'no_candidate',rejected_targets:[{target:'Rosette',basis:'non_positive_evaluation_score'}]};
  const protectedSnapshot=()=>page.evaluate(()=>JSON.stringify({configuration:state.configuration,draft:state.configurationDraft,missions:state.savedMissions,accepted:state.acceptedMission}));
  const box=page.locator('#message-continuation');
  for(const mode of ['simple','pro'])for(const width of [390,1280]){
   response=structuredClone(weather);
   await page.setViewportSize({width,height:1000});
   await page.evaluate(async ({config,mode})=>{
    applyUiMode(mode);state.configuration=structuredClone(config);state.configurationDraft=draftFromConfiguration(state.configuration);state.selectedProjectId=null;state.acceptedMission=null;state.savedMissions=[];state.currentDecision=null;state.pendingAcceptanceAttempt=null;state.acceptanceBlocked=false;await setDiscoveryMode(false);setView('availability');
   },{config,mode});
   if(mode==='simple')await page.locator('#beginner-project').selectOption('__nightmerit_compare_projects__');else await page.locator('#compare-projects').check();
   await page.locator('input[name="availability-mode"][value="all_night"]').check();
   await page.locator('#request-recommendation').click();await box.waitFor();
   const before=await protectedSnapshot(),count=writes.length;
   assert.match(await box.innerText(),/décision météo refuse/);
   await box.locator('[data-continuation-action="refresh"]').click();await page.waitForFunction(()=>!state.requestingRecommendation);
   assert.equal(writes.length,count+1);assert.equal(await protectedSnapshot(),before);
   for(const [data,match,absent] of [[complete,/Tous les objectifs/,/Une valeur manquante/],[missing,/Une valeur manquante/,/Tous les objectifs/],[mixed,/d’autres prises de vue/,/Tous les objectifs|d’autres projets/],[short,/35 min.*60 min/,/décision météo refuse/],[equipment,/filtre requis/,/décision météo refuse/],[unknown,/motif peut varier/,/décision météo refuse/]]){
    const raw=JSON.stringify(data);await page.evaluate(d=>showTonightUnavailable(d),data);
    assert.match(await box.innerText(),match);assert.doesNotMatch(await box.innerText(),absent);assert.equal(JSON.stringify(data),raw);
    assert.equal(await page.locator('.project-tonight-summary:visible').count(),0);
    assert.match(await box.innerText(),/aucun plan, séance ni crédit/);
    const bounds=await box.evaluate(el=>({left:el.getBoundingClientRect().left,right:el.getBoundingClientRect().right,overflow:el.scrollWidth>el.clientWidth}));assert(bounds.left>=0&&bounds.right<=width&&!bounds.overflow,JSON.stringify(bounds));
   }
   // An unfinished project can be retried even when the new panel has no refresh action.
   response=structuredClone(unknown);
   assert.equal(await box.locator('[data-continuation-action="refresh"]').count(),0);
   const beforeRetry=writes.length;
   assert.equal(await page.locator('#message-retry').isVisible(),true);
   await page.locator('#message-retry').click();await page.waitForFunction(()=>!state.requestingRecommendation);
   assert.equal(writes.length,beforeRetry+1);assert.equal(await protectedSnapshot(),before);
   assert.equal(await page.locator('#message-retry').isVisible(),true);
   // Completed or unknown goals keep their caller-imposed no-retry state.
   for(const data of [complete,missing,mixed]){
    await page.evaluate(d=>showTonightUnavailable(d),data);
    assert.equal(await page.locator('#message-retry').isVisible(),false);
   }
   let unchanged=writes.length;
   await box.locator('[data-continuation-action="projects"]').focus();await page.keyboard.press('Enter');
   await page.waitForFunction(()=>state.view==='projects');assert.equal(writes.length,unchanged);assert.equal(await protectedSnapshot(),before);
   await page.evaluate(d=>showTonightUnavailable(d),short);
   await box.locator('[data-continuation-action="hours"]').click();await page.waitForFunction(()=>state.view==='availability');assert.equal(writes.length,unchanged);assert.equal(await protectedSnapshot(),before);
   await page.evaluate(d=>showTonightUnavailable(d),equipment);
   await box.locator('[data-continuation-action="equipment"]').click();await page.waitForFunction(()=>state.view==='equipment');assert.equal(writes.length,unchanged);assert.equal(await protectedSnapshot(),before);
   await page.evaluate(d=>showTonightUnavailable(d),mixed);
   if(out){fs.mkdirSync(out,{recursive:true});await box.screenshot({path:path.join(out,`continuation-${mode}-${width}.png`)});}
   await page.evaluate(()=>showMessage('Autre état','Message suivant'));assert.equal(await box.isVisible(),false);
   cases.push({mode,width,completed_missing_mixed_weather_short_equipment_unknown:true,navigation_no_write:true,explicit_refresh_only:true,unfinished_refusal_retry_preserved:true,single_project_mixed_filters:true});
  }
  assert.deepEqual(errors,[]);assert.equal(writes.length,12);assert(writes.every(w=>w.path==='/v1/tonight'));
  if(out)fs.writeFileSync(path.join(out,'verification.json'),JSON.stringify({success:true,cases,writes,errors,http_intercepted:true,no_real_weather:true,no_session_or_credit_request:true},null,2));
  console.log('PASS: Comment continuer, 4 fictitious journeys, evidence-based refusal, unknown and mixed progress, click navigation, explicit refresh, no credit or mission writes');
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
