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
  for(const mode of ['simple','pro'])for(const width of [390,1280]){
   response=structuredClone(base);accepted=false;
   await page.setViewportSize({width,height:900});
   await page.evaluate(async ({config,mode})=>{
    applyUiMode(mode);state.configuration=structuredClone(config);state.configurationDraft=draftFromConfiguration(state.configuration);state.selectedProjectId=null;state.acceptedMission=null;state.savedMissions=[];state.currentDecision=null;state.pendingAcceptanceAttempt=null;state.acceptanceBlocked=false;await setDiscoveryMode(false);setView('availability');
   },{config,mode});
   if(mode==='simple')await page.locator('#beginner-project').selectOption('__nightmerit_compare_projects__');
   else await page.locator('#compare-projects').check();
   await page.locator('input[name="availability-mode"][value="all_night"]').check();
   await page.locator('#request-recommendation').click();await summary.waitFor();
   assert.match(await summary.innerText(),/Rosette — OIII/);
   assert.match(await summary.innerText(),/Objectif 3 h · Déjà acquis 40 min · Reste à faire 2 h 20/);
   assert.doesNotMatch(await summary.innerText(),/Déjà acquis 25 min|Déjà acquis 1 h/);
   const before=await snapshot(),count=writes.length;
   await summary.locator('summary').focus();await page.keyboard.press('Space');
   assert.match(await summary.locator('ul').innerText(),/Cible bien placée — Altitude favorable/);
   assert.match(await page.locator('#decision-warning').innerText(),/Passages nuageux/);
   await page.keyboard.press('Enter');
   const all=page.locator('.project-comparison > details');if(!(await all.evaluate(el=>el.open)))await all.locator(':scope > summary').click();
   assert.match(await all.innerText(),/M42/);assert.match(await all.innerText(),/SII : objectif 3 h · acquis 25 min/);
   assert.deepEqual(await snapshot(),before);assert.equal(writes.length,count);
   const bounds=await summary.evaluate(el=>({left:el.getBoundingClientRect().left,right:el.getBoundingClientRect().right,overflow:el.scrollWidth>el.clientWidth}));assert.ok(bounds.left>=0&&bounds.right<=width&&!bounds.overflow,JSON.stringify(bounds));
   if(out){fs.mkdirSync(out,{recursive:true});await page.locator('.project-comparison').screenshot({path:path.join(out,`summary-${mode}-${width}.png`)});}
   // An unknown value and missing explanation are not turned into a zero or a reason.
   const unknown=structuredClone(base);unknown.project_comparison[1].filters[0].acquired_hours=null;unknown.explanation={};
   await page.evaluate(d=>renderDecision(d),unknown);assert.match(await summary.innerText(),/Déjà acquis non renseigné/);
   await summary.locator('summary').click();assert.match(await summary.innerText(),/Aucune justification détaillée n’est disponible/);
   // No recommendation text is visible on a weather refusal.
   const refused={...structuredClone(base),status:'weather_refused',weather_decision:{admissibility:'refused',presentation:{label:'Refus météo fictif',summary:'Trop de nuages'}}};
   await page.evaluate(d=>showTonightUnavailable(d),refused);assert.equal(await page.locator('.project-tonight-summary:visible').count(),0);
   // Pending OIII/SII must stay unconfirmed after a mere selection.
   const pending={...structuredClone(base),status:'no_mission',creation_refusal:'preselection_evidence_cannot_authorize_mission',acquisition_intent_choice_available:true,acquisition_intent_selection_status:'no_clear_preference',selected_acquisition_intent_id:null,viable_acquisition_intent_ids:['r_oiii','r_sii'],acquisition_intent_options:[{acquisition_intent_id:'r_oiii',label:'OIII'},{acquisition_intent_id:'r_sii',label:'SII'}]};
   await page.evaluate(d=>{state.currentDecision=d;state.acceptedMission=null;renderDecision(d)},pending);
   assert.match(await summary.innerText(),/Filtre à confirmer/);assert.doesNotMatch(await summary.innerText(),/21:00|Déjà acquis 40 min|Déjà acquis 25 min/);
   await page.locator('#primary-intent').selectOption('r_sii');assert.match(await summary.innerText(),/Filtre à confirmer/);
   await page.locator('#open-mission').click();await page.waitForFunction(()=>state.acceptedMission?.mission_id==='mission-fictitious');
   assert(accepted);assert.match(await summary.locator('h3').textContent(),/Plan confirmé pour ce soir/);
   assert.match(await summary.textContent(),/Rosette — SII/);assert.match(await summary.textContent(),/Déjà acquis 25 min/);
   assert.match(await summary.textContent(),/22:00/);assert.match(await summary.textContent(),/Rosée à surveiller/);
   assert.doesNotMatch(await summary.textContent(),/Filtre à confirmer|Déjà acquis 40 min/);
   await page.locator('#close-mission').click();assert.equal(await summary.isVisible(),true);
   assert.deepEqual(await page.evaluate(()=>state.configuration),config);
   cases.push({mode,width,bounds,display_and_disclosures_unchanged_state:true,pending_and_confirmed_filter_checked:true});
  }
  assert.deepEqual(errors,[]);assert.equal(writes.filter(w=>w.path==='/v1/tonight').length,4);assert.equal(writes.filter(w=>w.path==='/v1/decision-selections').length,4);
  if(out)fs.writeFileSync(path.join(out,'verification.json'),JSON.stringify({success:true,cases,writes,errors,http_intercepted:true,no_real_weather:true,no_session_or_credit_request:true},null,2));
  console.log('PASS: Pour ce soir, 4 fictitious journeys, exact project/filter progress, disclosures, missing values, refusal, pending filter then server confirmation; no extra writes');
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
