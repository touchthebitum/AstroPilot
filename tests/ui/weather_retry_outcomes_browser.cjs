// Isolated fixture browser: only fictitious intercepted services are written.
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
  const page=await browser.newPage({timezoneId:'Europe/Zurich'}),writes=[],errors=[],cases=[],dialogs=[];
  const web=path.resolve(__dirname,'../../astropilot/web'),out=process.env.NIGHTMERIT_PROOF_DIR;
  const refused={...structuredClone(base),status:'no_mission',creation_refusal:'no_eligible_acquisition_intent',acquisition_intent_assessments:[{status:'not_eligible',label:'OIII',reason_codes:['required_filter_unavailable']}]};
  let httpStatus=200;
  let response=refused,serverConfig,inventory,revision,activeTargeted=false;
  const references=[{id:'fixture_ha',label:'Hα fictif',filter_type:'Ha',bandwidth_nm:7},{id:'fixture_oiii',label:'OIII fictif',filter_type:'OIII',bandwidth_nm:7},{id:'fixture_sii',label:'SII fictif',filter_type:'SII',bandwidth_nm:7}];
  page.on('pageerror',e=>errors.push(e.message));page.on('dialog',async d=>{dialogs.push(d.message());await d.dismiss()});
  await page.route('**/*',async route=>{
   const req=route.request(),url=new URL(req.url());assert.equal(url.origin,origin);
   const json=(data,status=200)=>route.fulfill({headers:timeHeaders,status,json:data});
   if(req.method()!=='GET'){
    const body=req.postDataJSON();writes.push({method:req.method(),path:url.pathname,body});
    if(url.pathname==='/v1/tonight'){assert.equal(req.method(),'POST');if(activeTargeted)assert.equal(body.selected_project_id,'Rosette');else assert.equal(body.compare_projects,true);if(response.transportFailure)return route.abort('failed');return json(response,httpStatus)}
    assert.equal(req.method(),'PUT');
    assert.equal(body.expected_revision,revision);
    if(url.pathname==='/v1/configuration'){
     revision++;serverConfig={...serverConfig,site:{...body.site,timezone:'Europe/Zurich'},projects:body.projects,active_equipment_id:body.equipment.preset_id,profile_revision:revision};return json(serverConfig);
    }
    assert.equal(url.pathname,'/v1/filter-inventory');assert.equal(body.equipment_id,'fixtureB');
    inventory[body.equipment_id]=body.inventory;return json({profile_revision:++revision});
   }
   const progressMatch=/^\/v1\/projects\/(Rosette|M42)\/progress$/.exec(url.pathname);
   if(progressMatch){const key=progressMatch[1],id=key+'_oiii',h=key==='Rosette'?40/60:1;
    return json({project_id:key,acquisition_intents:[{acquisition_intent_id:id,filter_type:'OIII'}],acquisition_intent_targets:[{acquisition_intent_id:id,target_hours:3}],intent_progress_breakdown:[{acquisition_intent_id:id,base_seconds:h*3600,credits_us:0,effective_total_seconds:h*3600,remaining_hours:3-h}]});
   }
   if(url.pathname==='/v1/configuration'&&serverConfig)return json({...serverConfig,profile_revision:revision});
   if(url.pathname==='/v1/filter-inventory'&&serverConfig){
    return json({profile_revision:revision,active_equipment_id:serverConfig.active_equipment_id,inventories:inventory,mount_inventories:{},references});
   }
   if(url.pathname==='/ui/timezone-data.js')return route.fulfill({headers:timeHeaders,contentType:'text/javascript',body:timeData});
   const file=url.pathname==='/'?'index.html':url.pathname.startsWith('/ui/')?url.pathname.slice(4):null;
   if(file&&path.basename(file)===file&&fs.existsSync(path.join(web,file)))return route.fulfill({headers:timeHeaders,contentType:file.endsWith('.js')?'text/javascript':file.endsWith('.css')?'text/css':'text/html',body:fs.readFileSync(path.join(web,file))});
   if(url.pathname==='/v1/demo-context')return json({enabled:false,weather:'real'});
   if(url.pathname==='/v1/execution-sessions')return json([]);
   return json({},503);
  });
  await page.goto(origin);await page.waitForFunction(()=>state.view==='configuration_error');
  const presets=['fixtureA','fixtureB'].map((id,i)=>({id,name:'Ensemble fictif '+i,kind:'preset',optics_manufacturer:'Fictif',optics_model:'Optique '+i,camera_manufacturer:'Fictif',camera_model:'Caméra '+i}));
  const config={configured:true,profile_revision:1,site:{name:'Buttes fictif',latitude:46.88812,longitude:6.55137,bortle:4,timezone:'Europe/Zurich'},active_equipment_id:'fixtureA',available_equipment:presets,preset_equipment:presets,projects:{Rosette:{hours:40/60,target_hours:3},M42:{hours:1,target_hours:2}}};
  const requests=()=>writes.filter(w=>w.path==='/v1/tonight').length;
  const snapshot=()=>page.evaluate(()=>JSON.stringify({projects:state.configuration.projects,missions:state.savedMissions,accepted:state.acceptedMission}));
  const observations=[];
  const scenarios=['favorable','refus','panne','network','first-search'].flatMap(outcome=>[390,1280].map(width=>({mounting:'single',width,targeted:true,outcome})));
  for(const scenario of scenarios){
   const {mounting,width,targeted}=scenario;
   httpStatus=200;response=structuredClone(refused);activeTargeted=targeted;
   if(targeted){response.status='weather_refused';response.decision_id='previous-refusal';delete response.project_comparison;
    response.weather_decision={admissibility:'refused',presentation:{label:'Ciel trop couvert',summary:'Les nuages empêchent de préparer une mission sur les horaires évalués.'}};}

   revision=1;serverConfig=structuredClone(config);
   inventory={fixtureA:{wheel_name:'Filtre monté seul',slot_count:1,slots:[{position:1,label:'Hα fictif',filter_type:'Ha',bandwidth_nm:7,filter_profile_id:'fixture_ha'}]}};
   const originalInventory=JSON.stringify(inventory.fixtureA),start=writes.length,initialRequests=requests();
   await page.setViewportSize({width,height:1000});
   await page.evaluate(async config=>{
    applyUiMode('simple');state.refusedSearchResume=null;state.configuration=structuredClone(config);state.configurationDraft=draftFromConfiguration(state.configuration);state.selectedProjectId=null;state.acceptedMission=null;state.savedMissions=[];state.currentDecision=null;state.pendingAcceptanceAttempt=null;state.acceptanceBlocked=false;state.decisionSiteReloadRequired=false;await setDiscoveryMode(false);prefillConfiguration();setView('availability');
   },config);
   await page.locator('#beginner-project').selectOption(targeted?'Rosette':'__nightmerit_compare_projects__');
   await page.locator('input[name="availability-mode"][value="fixed_window"]').check();
   await page.locator('#availability-preparation-minutes').evaluate(el=>el.closest('details').open=true);
   await page.locator('#availability-start').fill('2026-11-21T20:00');await page.locator('#availability-end').fill('2026-11-21T23:30');
   await page.locator('#availability-preparation-minutes').fill('20');await page.locator('#availability-flats-minutes').fill('5');
   const protectedBefore=await snapshot();
   if(scenario.outcome==='first-search'){
    httpStatus=503;response={detail:{code:'weather_unavailable'}};
    await page.locator('#request-recommendation').click();await page.waitForFunction(()=>!state.requestingRecommendation);
    const error=await page.locator('#availability-error').innerText();
    assert.match(error,/L’analyse n’a pas abouti/);assert.match(error,/Aucun nouveau résultat/);assert(!error.includes('refus précédent'));
    assert.equal(await page.evaluate(()=>state.currentDecision),null);assert.equal(requests(),initialRequests+1);assert.equal(await snapshot(),protectedBefore);
    assert.equal(await page.locator('#availability-preparation-minutes').inputValue(),'20');assert.equal(await page.locator('#availability-flats-minutes').inputValue(),'5');
    const bounds=await page.locator('#availability-error').boundingBox();assert(bounds.y>=0&&bounds.y+bounds.height<=1000);
    await page.evaluate(()=>setView('review'));assert.equal(await page.locator('#availability-error').isVisible(),false);
    await page.evaluate(()=>setView('availability'));assert.equal(await page.locator('#availability-error').isVisible(),true);
    cases.push({width,outcome:scenario.outcome,without_previous_refusal:true,no_automatic_search:true,counters_unchanged:true});
    if(out)await page.screenshot({path:path.join(out,`outcome-first-search-${width}.png`),fullPage:true});
    continue;
   }
   await page.locator('#request-recommendation').click();await page.locator('#message-edit-availability').click();
   if(!(await page.locator('#beginner-context-details').evaluate(el=>el.open)))await page.locator('#beginner-context-details > summary').click();
   await page.getByRole('button',{name:'Modifier mon site ou mon matériel',exact:true}).click();await page.locator('#site-next').click();
   await page.waitForFunction(()=>state.view==='equipment');
   // Use the real optics/camera/filter wizard, with no bypass of its return path.
   await page.locator('input[name="preset-equipment"][value="fixtureB"]').check();
   await page.locator('#equipment-next').click();assert.match(await page.locator('#equipment-title').innerText(),/caméra/);
   await page.locator('#equipment-next').click();
   const dialog=page.locator('.wheel-inventory-dialog');await dialog.waitFor();

   assert.match(await dialog.innerText(),/Comment utilisez-vous vos filtres/);
   await dialog.locator(`input[name="initial-filter-mounting"][value="${mounting}"]`).check();
   await dialog.getByRole('button',{name:'Continuer vers les filtres disponibles',exact:true}).click();
   if(out){fs.mkdirSync(out,{recursive:true});await dialog.screenshot({path:path.join(out,`filter-step-${mounting}-${width}.png`)});fs.writeFileSync(path.join(out,`filter-step-${mounting}-${width}.html`),await dialog.innerHTML())}
   await dialog.locator('fieldset').first().locator('select').first().selectOption('fixture_oiii');

   const expectedLabel='Enregistrer les filtres et reprendre ma recherche';
   const save=dialog.getByRole('button',{name:expectedLabel,exact:true});
   await save.click();await page.waitForFunction(()=>state.view==='availability');
   assert.equal(await dialog.isVisible(),false);assert.equal(await snapshot(),protectedBefore);
   assert.equal(JSON.stringify(inventory.fixtureA),originalInventory);assert.equal(inventory.fixtureB.slots.length,mounting==='single'?1:mounting==='wheel'?2:0);
   assert.equal(await page.locator('#projects-step').isVisible(),false);
   const resume=page.locator('#search-resume');await resume.waitFor();
   assert.match(await resume.innerText(),targeted?/Projet : Rosette/:/Comparaison de mes projets/);
   assert.match(await resume.innerText(),/20:00.*23:30/);assert.match(await resume.innerText(),/Préparation : 20 min · Flats : 5 min/);
   assert.match(await resume.innerText(),/matériel et vos choix de filtres sont enregistrés/);assert.match(await resume.innerText(),/recherche n’a pas été relancée/);
   const submit=page.locator('#request-recommendation');
   const expectLiveLabel=async(expected)=>{
    await page.waitForFunction(expected=>{
     const label=document.querySelector('#request-recommendation').textContent.trim();
     return label===expected && document.querySelector('#search-resume-action')?.textContent.includes(`« ${label} »`);
    },expected);
    assert.match(await resume.innerText(),/réévaluer les conditions météo et votre créneau/);
   };
   await expectLiveLabel(targeted?'Vérifier mon projet':'Quel projet avancer ce soir ?');
   await page.evaluate(()=>applyUiMode('pro'));await expectLiveLabel(targeted?'Préparer ma nuit':'Quel projet avancer ce soir ?');
   assert.equal(await submit.innerText(),targeted?'Préparer ma nuit':'Quel projet avancer ce soir ?');
   await page.evaluate(()=>applyUiMode('simple'));await expectLiveLabel(targeted?'Vérifier mon projet':'Quel projet avancer ce soir ?');
   assert.equal(await submit.innerText(),targeted?'Vérifier mon projet':'Quel projet avancer ce soir ?');
   const beforeLinkRequests=requests(),beforeLink=await snapshot();
   const link=resume.getByRole('link',{name:'Aller au bouton de recherche',exact:true});
   assert.equal(await link.getAttribute('href'),'#request-recommendation');
   await link.click();assert.equal(await submit.evaluate(el=>el===document.activeElement),true);
   await link.focus();await page.keyboard.press('Enter');
   assert.equal(await submit.evaluate(el=>el===document.activeElement),true);
   const buttonBounds=await submit.boundingBox();assert(buttonBounds.y>=0&&buttonBounds.y+buttonBounds.height<=1000);
   await page.waitForTimeout(150);assert.equal(requests(),beforeLinkRequests);assert.equal(await snapshot(),beforeLink);
   if(out){await page.screenshot({path:path.join(out,`weather-return-${mounting}-${width}.png`),fullPage:true});
    fs.writeFileSync(path.join(out,`weather-return-${mounting}-${width}.json`),JSON.stringify({buttonLabel:await submit.innerText(),summary:await resume.innerText(),link_focuses_existing_button:true,keyboard_and_pointer:true,no_automatic_analysis:true},null,2));}
   const bounds=await resume.evaluate(el=>({left:el.getBoundingClientRect().left,right:el.getBoundingClientRect().right,overflow:el.scrollWidth>el.clientWidth}));assert(bounds.left>=0&&bounds.right<=width&&!bounds.overflow,JSON.stringify(bounds));
   if(out)await resume.screenshot({path:path.join(out,`resume-${mounting}-${width}.png`)});
   assert.equal(await page.locator('#availability-start').inputValue(),'2026-11-21T20:00');assert.equal(await page.locator('#availability-end').inputValue(),'2026-11-21T23:30');
   assert.equal(await page.evaluate(()=>state.configuration.active_equipment_id),'fixtureB');assert.equal(requests(),initialRequests+1);
   assert.equal(requests(),initialRequests+1);
   assert.equal(await page.evaluate(()=>state.currentDecision?.decision_id),'previous-refusal');
   if(scenario.outcome==='favorable'){
    response=structuredClone(base);response.decision_id='new-favorable';delete response.project_comparison;
    response.weather_trust.retrieved_at_utc='2026-11-21T18:30:00Z';
   }else if(scenario.outcome==='refus'){
    response={...structuredClone(base),status:'weather_refused',decision_id:'new-refusal',weather_decision:{admissibility:'refused',presentation:{label:'Ciel trop couvert',summary:'Les nuages empêchent de préparer une mission sur les horaires évalués.'}}};
    delete response.project_comparison;response.weather_trust.retrieved_at_utc='2026-11-21T18:30:00Z';
   }else if(scenario.outcome==='network'){response={transportFailure:true};}else{httpStatus=503;response={detail:{code:'weather_unavailable'}};}
   await page.locator('#request-recommendation').click();await page.waitForFunction(()=>!state.requestingRecommendation);
   await page.waitForTimeout(150);
   assert.equal(requests(),initialRequests+2);assert.equal(await snapshot(),protectedBefore);
   assert.equal(await page.locator('#search-resume').isVisible(),false);
   const result={outcome:scenario.outcome,width,view:await page.evaluate(()=>state.view),decision_id:await page.evaluate(()=>state.currentDecision?.decision_id||null),
    error:await page.locator('#availability-error').innerText(),errorVisible:await page.locator('#availability-error').isVisible(),
    decisionVisible:await page.locator('#decision').isVisible(),refusalVisible:await page.locator('#message-state').isVisible(),
    visibleText:await page.locator('body').innerText(),hours:[await page.locator('#availability-start').inputValue(),await page.locator('#availability-end').inputValue()],
    preparation:await page.locator('#availability-preparation-minutes').inputValue(),flats:await page.locator('#availability-flats-minutes').inputValue(),
    no_new_mission_or_credit:true,analysis_requests_this_case:requests()-initialRequests};
   assert.deepEqual(result.hours,['2026-11-21T20:00','2026-11-21T23:30']);assert.equal(result.preparation,'20');assert.equal(result.flats,'5');
   if(scenario.outcome==='favorable'){assert(result.decisionVisible);assert(!result.refusalVisible);assert.equal(result.decision_id,'new-favorable');assert(!result.errorVisible);}
   else if(scenario.outcome==='refus'){assert(!result.decisionVisible);assert(result.refusalVisible);assert.equal(result.decision_id,'new-refusal');assert(!result.errorVisible);assert.match(result.visibleText,/Ciel trop couvert/);}
   else{assert(!result.decisionVisible);assert(!result.refusalVisible);assert.equal(result.decision_id,null);assert(result.errorVisible);assert.match(result.error,scenario.outcome==='network'?/Connexion impossible/:/Météo temporairement indisponible/);assert.match(result.error,/Aucun nouveau résultat/);assert.match(result.error,/Le refus précédent n’a pas été réévalué/);
    const errorBounds=await page.locator('#availability-error').boundingBox();assert(errorBounds.y>=0&&errorBounds.y+errorBounds.height<=1000);
    assert.equal(await page.locator('#availability-error').getAttribute('role'),'alert');}
   const segment=writes.slice(start);assert.equal(segment.length,4);assert.equal(segment.filter(w=>w.path==='/v1/configuration').length,1);assert.equal(segment.filter(w=>w.path==='/v1/filter-inventory').length,1);
   observations.push(result);cases.push({width,outcome:scenario.outcome,no_automatic_search:true,hours_and_20_5_preserved:true,counters_unchanged:true,old_decision_not_displayed:true});
   if(out){await page.screenshot({path:path.join(out,`outcome-${scenario.outcome}-${width}.png`),fullPage:true});fs.writeFileSync(path.join(out,`outcome-${scenario.outcome}-${width}.json`),JSON.stringify(result,null,2));}
   if(['panne','network'].includes(scenario.outcome)){
    httpStatus=200;response=structuredClone(base);response.decision_id='recovery';delete response.project_comparison;
    await page.locator('#request-recommendation').click();await page.waitForFunction(()=>!state.requestingRecommendation);
    assert.equal(requests(),initialRequests+3);assert.equal(await snapshot(),protectedBefore);
    assert.equal(await page.locator('#availability-error').innerText(),'');assert.equal(await page.locator('#availability-error').isVisible(),false);
    assert.equal(await page.evaluate(()=>state.currentDecision.decision_id),'recovery');assert.equal(await page.locator('#decision').isVisible(),true);
   }


  }
  assert.deepEqual(errors,[]);assert.deepEqual(dialogs,[]);
  if(out)fs.writeFileSync(path.join(out,'verification.json'),JSON.stringify({success:true,observations,source_base:'694f27ffd7dddc3ed007d2ac800146f3ebca7ec5',cases,writes,errors,dialogs,http_intercepted:true,no_personal_profile:true},null,2));
  console.log('PASS: 10 parcours fictifs à 390/1280 : favorable, refus, panne 503, réseau, première recherche ; reprise favorable, alerte en haut, 20/5 et compteurs conservés');
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
