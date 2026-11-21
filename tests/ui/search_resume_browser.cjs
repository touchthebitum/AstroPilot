// A separate browser, fictitious profiles and fully intercepted HTTP only.
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
 try{
  const page=await browser.newPage({timezoneId:'Europe/Zurich'}),writes=[],errors=[],cases=[];
  const web=path.resolve(__dirname,'../../astropilot/web'),out=process.env.NIGHTMERIT_PROOF_DIR;
  const short={...structuredClone(base),status:'no_productive_window',actionability_refusal:{conclusion:'no_productive_window',status:'constraints_refusal',refusal_stage:'continuous_window_too_short',best_productive_window_minutes:35,required_continuous_minutes:60}};
  const equipment={...structuredClone(base),status:'no_mission',creation_refusal:'no_eligible_acquisition_intent',acquisition_intent_assessments:[{status:'not_eligible',label:'OIII',reason_codes:['required_filter_unavailable']}]};
  let response=short,serverConfig;
  page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/*',async route=>{
   const req=route.request(),url=new URL(req.url());assert.equal(url.origin,origin);
   const json=(data,status=200)=>route.fulfill({headers:timeHeaders,status,json:data});
   if(req.method()!=='GET'){
    const body=req.postDataJSON();writes.push({method:req.method(),path:url.pathname,body});
    if(url.pathname==='/v1/tonight'){assert.equal(req.method(),'POST');assert.equal(body.compare_projects,true);return json(response)}
    assert.equal(url.pathname,'/v1/configuration');assert.equal(req.method(),'PUT');
    serverConfig={...serverConfig,site:{...body.site,timezone:'Europe/Zurich'},projects:body.projects,active_equipment_id:body.equipment.preset_id,profile_revision:serverConfig.profile_revision+1};
    return json(serverConfig);
   }
   if(url.pathname==='/ui/timezone-data.js')return route.fulfill({headers:timeHeaders,contentType:'text/javascript',body:timeData});
   const file=url.pathname==='/'?'index.html':url.pathname.startsWith('/ui/')?url.pathname.slice(4):null;
   if(file&&path.basename(file)===file&&fs.existsSync(path.join(web,file)))return route.fulfill({headers:timeHeaders,contentType:file.endsWith('.js')?'text/javascript':file.endsWith('.css')?'text/css':'text/html',body:fs.readFileSync(path.join(web,file))});
   if(url.pathname==='/v1/demo-context')return json({enabled:false,weather:'real'});
   if(url.pathname==='/v1/execution-sessions')return json([]);
   return json({},503);
  });
  await page.goto(origin);await page.waitForFunction(()=>state.view==='configuration_error');
  const presets=['fixtureA','fixtureB'].map((id,i)=>({id,name:'Ensemble fictif '+i,kind:'preset',optics_manufacturer:'Fictif',optics_model:'135 mm',camera_manufacturer:'Fictif',camera_model:'Monochrome'}));
  const config={configured:true,profile_revision:1,site:{name:'Buttes fictif',latitude:46.88812,longitude:6.55137,bortle:4,timezone:'Europe/Zurich'},active_equipment_id:'fixtureA',available_equipment:presets,preset_equipment:presets,projects:{Rosette:{hours:40/60,target_hours:3},M42:{hours:1,target_hours:2}}};
  const resume=page.locator('#search-resume');
  const counters=()=>page.evaluate(()=>JSON.stringify({projects:state.configuration.projects,saved:state.savedMissions,accepted:state.acceptedMission}));
  const requests=()=>writes.filter(w=>w.path==='/v1/tonight').length;
  for(const mode of ['simple','pro'])for(const width of [390,1280]){
   response=structuredClone(short);serverConfig=structuredClone(config);
   await page.setViewportSize({width,height:1000});
   await page.evaluate(async({config,mode})=>{
    applyUiMode(mode);state.refusedSearchResume=null;state.configuration=structuredClone(config);state.configurationDraft=draftFromConfiguration(state.configuration);state.selectedProjectId=null;state.acceptedMission=null;state.savedMissions=[];state.currentDecision=null;state.pendingAcceptanceAttempt=null;state.acceptanceBlocked=false;state.decisionSiteReloadRequired=false;await setDiscoveryMode(false);prefillConfiguration();setView('availability');
   },{config,mode});
   assert.equal(await resume.isVisible(),false);
   if(mode==='simple')await page.locator('#beginner-project').selectOption('__nightmerit_compare_projects__');else await page.locator('#compare-projects').check();
   await page.locator('input[name="availability-mode"][value="fixed_window"]').check();
   // These operational fields live inside a disclosure: expose it before editing.
   await page.locator('#availability-preparation-minutes').evaluate(el=>el.closest('details').open=true);
   await page.locator('#availability-start').fill('2026-11-21T20:00');await page.locator('#availability-end').fill('2026-11-21T23:30');
   await page.locator('#availability-preparation-minutes').fill('20');await page.locator('#availability-flats-minutes').fill('5');
   const protectedBefore=await counters(),count=requests();
   await page.locator('#request-recommendation').click();await page.locator('#message-continuation').waitFor();
   assert.equal(requests(),count+1);assert.equal(await resume.isVisible(),false);
   await page.locator('[data-continuation-action="hours"]').click();await resume.waitFor();
   assert.match(await resume.innerText(),/Comparaison de mes projets/);assert.match(await resume.innerText(),/Buttes fictif/);
   assert.match(await resume.innerText(),/20:00.*23:30/);assert.match(await resume.innerText(),/Préparation : 20 min · Flats : 5 min/);
   assert.match(await resume.innerText(),/précédent refus n’a pas été réévalué/);assert.equal(requests(),count+1);
   await page.locator('#availability-start').fill('2026-11-21T21:00');await page.locator('#availability-preparation-minutes').fill('25');await page.locator('#availability-flats-minutes').fill('6');
   assert.match(await resume.innerText(),/21:00.*23:30/);assert.match(await resume.innerText(),/Préparation : 25 min · Flats : 6 min/);assert.equal(requests(),count+1);assert.equal(await counters(),protectedBefore);
   if(mode==='simple'){
    await page.locator('#beginner-project').selectOption('Rosette');
    await page.waitForFunction(()=>!state.compareProjects&&state.selectedProjectId==='Rosette');
    assert.match(await resume.innerText(),/Projet : Rosette/);
    await page.locator('#beginner-project').selectOption('__nightmerit_compare_projects__');
    await page.waitForFunction(()=>state.compareProjects);
    assert.match(await resume.innerText(),/Comparaison de mes projets/);assert.equal(requests(),count+1);
   }
   const bounds=await resume.evaluate(el=>({left:el.getBoundingClientRect().left,right:el.getBoundingClientRect().right,overflow:el.scrollWidth>el.clientWidth}));assert(bounds.left>=0&&bounds.right<=width&&!bounds.overflow,JSON.stringify(bounds));
   if(out){fs.mkdirSync(out,{recursive:true});await resume.screenshot({path:path.join(out,`resume-${mode}-${width}.png`)})}
   response=structuredClone(equipment);await page.locator('#request-recommendation').click();await page.locator('[data-continuation-action="equipment"]').waitFor();
   assert.equal(requests(),count+2);assert.equal(await resume.isVisible(),false);
   assert.equal(writes.at(-1).body.availability.preparation_minutes,25);assert.equal(writes.at(-1).body.availability.flats_minutes,6);assert.match(writes.at(-1).body.availability.start_local,/21:00/);
   await page.locator('[data-continuation-action="equipment"]').click();await page.waitForFunction(()=>state.view==='equipment');assert.equal(await resume.isVisible(),false);
   // Arrange the return from an equipment editor with a pending local choice.
   // Exercise the actual save handler below; no personal profile or server is used.
   await page.evaluate(()=>{state.configurationDraft.equipment={preset_id:'fixtureB'};setView('availability')});
   assert.match(await resume.innerText(),/Configuration modifiée.*enregistrez vos réglages/);assert.equal(requests(),count+2);
   await page.locator('#request-recommendation').click();await page.waitForFunction(()=>state.view==='review');assert.equal(requests(),count+2);
   assert.equal(await page.locator('#configuration-form-error').isVisible(),true);assert.match(await page.locator('#configuration-form-error').innerText(),/Enregistrez vos réglages/);
   await page.locator('#save-configuration').click();await page.waitForFunction(()=>state.view==='availability'&&!state.savingConfiguration);
   assert.doesNotMatch(await resume.innerText(),/Configuration modifiée/);assert.match(await resume.innerText(),/25 min.*6 min/);assert.equal(await counters(),protectedBefore);
   // A fictitious configuration reload invokes the real site invalidation path.
   await page.evaluate(()=>{const changed=structuredClone(state.configuration);changed.site={...changed.site,name:'Autre site fictif',latitude:47};initializeConfiguration(changed);setView('availability')});
   assert.equal(await page.locator('#availability-start').inputValue(),'');assert.equal(await page.locator('#availability-end').inputValue(),'');
   assert.match(await resume.innerText(),/site ou son fuseau a changé/);assert.match(await resume.innerText(),/Du à renseigner au à renseigner/);
   await page.locator('#request-recommendation').click();assert.equal(requests(),count+2);assert.equal(await resume.isVisible(),true);
   await page.locator('#availability-start').fill('2026-11-22T23:00');await page.locator('#availability-end').fill('2026-11-22T01:00');
   assert.match(await resume.innerText(),/23.11.2026 à 01:00/);
   response=structuredClone(base);await page.locator('#request-recommendation').click();await page.waitForFunction(()=>!state.requestingRecommendation);
   assert.equal(requests(),count+3);assert.equal(await resume.isVisible(),false);assert.equal(await page.evaluate(()=>state.refusedSearchResume),null);assert.equal(await counters(),protectedBefore);
   cases.push({mode,width,bounds,current_fields:true,no_automatic_search:true,pending_equipment_notice_and_explicit_save:true,changed_site_empty_hours:true,overnight:true,summary_cleared_on_new_search:true,counters_unchanged:true});
  }
  assert.deepEqual(errors,[]);assert.equal(requests(),12);assert.equal(writes.filter(w=>w.path==='/v1/configuration').length,4);
  if(out)fs.writeFileSync(path.join(out,'verification.json'),JSON.stringify({success:true,cases,writes,errors,http_intercepted:true,no_real_weather:true,no_session_or_credit_request:true},null,2));
  console.log('PASS: Reprendre ma recherche, 4 fictitious journeys; live inputs, equipment save, changed site, overnight, explicit searches only, no mission or credit writes');
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
