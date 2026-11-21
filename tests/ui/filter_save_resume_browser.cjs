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
  let response=refused,serverConfig,inventory,revision,activeTargeted=false,delayFilter=false,releaseFilter=null,serverChange=null,changeApplied=false;
  const references=[{id:'fixture_ha',label:'Hα fictif',filter_type:'Ha',bandwidth_nm:7},{id:'fixture_oiii',label:'OIII fictif',filter_type:'OIII',bandwidth_nm:7},{id:'fixture_sii',label:'SII fictif',filter_type:'SII',bandwidth_nm:7}];
  page.on('pageerror',e=>errors.push(e.message));page.on('dialog',async d=>{dialogs.push(d.message());await d.dismiss()});
  await page.route('**/*',async route=>{
   const req=route.request(),url=new URL(req.url());assert.equal(url.origin,origin);
   const json=(data,status=200)=>route.fulfill({headers:timeHeaders,status,json:data});
   if(req.method()!=='GET'){
    const body=req.postDataJSON();writes.push({method:req.method(),path:url.pathname,body});
    if(url.pathname==='/v1/tonight'){assert.equal(req.method(),'POST');if(activeTargeted)assert.equal(body.selected_project_id,'Rosette');else assert.equal(body.compare_projects,true);return json(response)}
    assert.equal(req.method(),'PUT');
    if(url.pathname==='/v1/filter-inventory'&&serverChange==='onSave'&&!changeApplied){
     serverConfig={...serverConfig,active_equipment_id:'fixtureA',profile_revision:++revision};changeApplied=true;
     return json({detail:{code:'inventory_revision_conflict'}},409);
    }
    assert.equal(body.expected_revision,revision);
    if(url.pathname==='/v1/configuration'){
     revision++;serverConfig={...serverConfig,site:{...body.site,timezone:'Europe/Zurich'},projects:body.projects,active_equipment_id:body.equipment.preset_id,profile_revision:revision};return json(serverConfig);
    }
    assert.equal(url.pathname,'/v1/filter-inventory');assert.equal(body.equipment_id,'fixtureB');
    inventory[body.equipment_id]=body.inventory;const savedRevision=++revision;if(delayFilter){await new Promise(resolve=>{releaseFilter=resolve});delayFilter=false}return json({profile_revision:savedRevision});
   }
   const progressMatch=/^\/v1\/projects\/(Rosette|M42)\/progress$/.exec(url.pathname);
   if(progressMatch){const key=progressMatch[1],id=key+'_oiii',h=key==='Rosette'?40/60:1;
    return json({project_id:key,acquisition_intents:[{acquisition_intent_id:id,filter_type:'OIII'}],acquisition_intent_targets:[{acquisition_intent_id:id,target_hours:3}],intent_progress_breakdown:[{acquisition_intent_id:id,base_seconds:h*3600,credits_us:0,effective_total_seconds:h*3600,remaining_hours:3-h}]});
   }
   if(url.pathname==='/v1/configuration'&&serverConfig)return json({...serverConfig,profile_revision:revision});
   if(url.pathname==='/v1/filter-inventory'&&serverConfig){
    if(serverChange&&serverChange!=='onSave'&&!changeApplied){
     serverConfig={...serverConfig,active_equipment_id:serverChange==='equipment'?'fixtureA':serverConfig.active_equipment_id,profile_revision:++revision};changeApplied=true;
    }
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
  const scenarios=[
   {mounting:'single',width:390,targeted:true}, {mounting:'single',width:1280,targeted:true},
   {mounting:'wheel',width:390}, {mounting:'wheel',width:1280},
   {mounting:'none',width:390}, {mounting:'single',width:1280,ordinary:true}, {mounting:'wheel',width:1280,late:true},
   {mounting:'single',width:390,serverChange:'equipment'}, {mounting:'wheel',width:1280,serverChange:'equipment'},
   {mounting:'single',width:1280,serverChange:'revision'}, {mounting:'wheel',width:390,serverChange:'revision'},
   {mounting:'single',width:390,serverChange:'onSave'}, {mounting:'wheel',width:1280,serverChange:'onSave'},
  ];
  for(const scenario of scenarios){
   const {mounting,width,targeted=false,ordinary=false,late=false}=scenario;
   response=structuredClone(refused);activeTargeted=targeted;delayFilter=late;releaseFilter=null;serverChange=scenario.serverChange||null;changeApplied=false;
   if(targeted){response.status='no_productive_window';delete response.project_comparison;response.actionability_refusal={conclusion:'no_productive_window',status:'constraints_refusal',refusal_stage:'continuous_window_too_short',best_productive_window_minutes:35,required_continuous_minutes:60};}
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
   if(ordinary){
    if(!(await page.locator('#beginner-context-details').evaluate(el=>el.open)))await page.locator('#beginner-context-details > summary').click();
    await page.getByRole('button',{name:'Modifier mon site ou mon matériel',exact:true}).click();await page.locator('#site-next').click();
   }else if(targeted){
    await page.locator('#request-recommendation').click();await page.locator('#message-edit-availability').click();
    if(!(await page.locator('#beginner-context-details').evaluate(el=>el.open)))await page.locator('#beginner-context-details > summary').click();
    await page.getByRole('button',{name:'Modifier mon site ou mon matériel',exact:true}).click();await page.locator('#site-next').click();
   }else{
    await page.locator('#request-recommendation').click();await page.locator('[data-continuation-action="equipment"]').click();
   }
   await page.waitForFunction(()=>state.view==='equipment');
   // Use the real optics/camera/filter wizard, with no bypass of its return path.
   await page.locator('input[name="preset-equipment"][value="fixtureB"]').check();
   await page.locator('#equipment-next').click();assert.match(await page.locator('#equipment-title').innerText(),/caméra/);
   await page.locator('#equipment-next').click();
   const dialog=page.locator('.wheel-inventory-dialog');await dialog.waitFor();

   if(serverChange){
    if(serverChange==='onSave'){
     await dialog.locator(`input[name="initial-filter-mounting"][value="${mounting}"]`).check();
     await dialog.getByRole('button',{name:'Continuer vers les filtres disponibles',exact:true}).click();
     if(mounting==='wheel'){
      await dialog.getByLabel('Nombre d’emplacements',{exact:true}).fill('2');await dialog.getByLabel('Nombre d’emplacements',{exact:true}).press('Tab');
     }
     await dialog.locator('fieldset').first().locator('select').first().selectOption('fixture_oiii');
     if(mounting==='wheel'){
      await dialog.getByRole('button',{name:'Emplacement suivant',exact:true}).click();
      await dialog.locator('fieldset').nth(1).locator('select').first().selectOption('fixture_sii');
     }
     await dialog.getByRole('button',{name:'Enregistrer les filtres et reprendre ma recherche',exact:true}).click();
     await dialog.getByRole('button',{name:'Relire et vérifier ma configuration',exact:true}).waitFor();
    }
    assert.match(await dialog.innerText(),/Vos réglages doivent être relus/);
    assert.match(await dialog.innerText(),/Aucun filtre n’a été enregistré/);
    assert.equal(await page.evaluate(()=>state.decisionSiteReloadRequired),true);
    assert.equal(await page.evaluate(()=>state.configuration.profile_revision),2);
    assert.equal(revision,3);assert.equal(requests(),initialRequests+1);
    assert.equal(writes.slice(start).filter(w=>w.path==='/v1/filter-inventory').length,serverChange==='onSave'?1:0);
    assert.equal(await page.evaluate(()=>state.view),'equipment');
    if(out){fs.mkdirSync(out,{recursive:true});await dialog.screenshot({path:path.join(out,`reload-${serverChange}-${width}.png`)})}
    await dialog.getByRole('button',{name:'Relire et vérifier ma configuration',exact:true}).click();
    await page.waitForFunction(()=>state.view==='review');
    assert.equal(await page.evaluate(()=>state.configuration.profile_revision),3);
    assert.equal(await page.evaluate(()=>state.configuration.active_equipment_id),serverConfig.active_equipment_id);
    assert.equal(await page.evaluate(()=>state.decisionSiteReloadRequired),false);
    assert.equal(writes.slice(start).length,serverChange==='onSave'?3:2,'reloading must not write or analyse');
    await page.locator('#save-configuration').click();await page.waitForFunction(()=>state.view==='availability'&&!state.savingConfiguration);
    assert.equal(await page.evaluate(()=>state.configuration.profile_revision),4);
    assert.equal(await page.evaluate(()=>state.configuration.active_equipment_id),serverConfig.active_equipment_id);
    assert.equal(await page.locator('#availability-start').inputValue(),'2026-11-21T20:00');
    assert.equal(await page.locator('#availability-end').inputValue(),'2026-11-21T23:30');
    assert.equal(await page.locator('#availability-preparation-minutes').inputValue(),'20');
    assert.equal(await page.locator('#availability-flats-minutes').inputValue(),'5');
    assert.equal(requests(),initialRequests+1);assert.equal(await snapshot(),protectedBefore);
    response=structuredClone(refused);await page.locator('#request-recommendation').click();await page.waitForFunction(()=>!state.requestingRecommendation);
    assert.equal(requests(),initialRequests+2);assert.equal(await snapshot(),protectedBefore);
    assert.equal(writes.slice(start).filter(w=>w.path==='/v1/filter-inventory').length,serverChange==='onSave'?1:0);
    assert.equal(JSON.stringify(inventory.fixtureA),originalInventory);assert.equal(inventory.fixtureB,undefined);
    cases.push({mounting,width,serverChange,mismatch_blocks_inventory_write_and_search:true,explicit_reload_then_review_and_save:true,client_server_equipment_and_revision_match:true,hours_and_20_5_preserved:true,counters_unchanged:true});continue;
   }
   assert.match(await dialog.innerText(),/Comment utilisez-vous vos filtres/);
   await dialog.locator(`input[name="initial-filter-mounting"][value="${mounting}"]`).check();
   await dialog.getByRole('button',{name:'Continuer vers les filtres disponibles',exact:true}).click();
   if(out){fs.mkdirSync(out,{recursive:true});await dialog.screenshot({path:path.join(out,`filter-step-${mounting}-${width}.png`)});fs.writeFileSync(path.join(out,`filter-step-${mounting}-${width}.html`),await dialog.innerHTML())}
   if(mounting==='single')await dialog.locator('fieldset').first().locator('select').first().selectOption('fixture_oiii');
   else if(mounting==='wheel'){
    await dialog.getByLabel('Nombre d’emplacements',{exact:true}).fill('2');await dialog.getByLabel('Nombre d’emplacements',{exact:true}).press('Tab');
    await dialog.locator('fieldset').nth(0).locator('select').first().selectOption('fixture_oiii');
    await dialog.getByRole('button',{name:'Emplacement suivant',exact:true}).click();
    await dialog.locator('fieldset').nth(1).locator('select').first().selectOption('fixture_sii');
   }

   const expectedLabel=ordinary?'Enregistrer et continuer vers le choix de cible':'Enregistrer les filtres et reprendre ma recherche';
   const save=dialog.getByRole('button',{name:expectedLabel,exact:true});
   if(late){
    await save.click();const deadline=Date.now()+10000;while(!releaseFilter&&Date.now()<deadline)await new Promise(resolve=>setTimeout(resolve,10));assert(releaseFilter,'filter save request was not emitted');
    await dialog.getByRole('button',{name:'Retour à la caméra',exact:true}).click();
    const cancelledRevision=await page.evaluate(()=>state.viewRevision);releaseFilter();
    await page.waitForFunction(()=>!document.querySelector('.wheel-inventory-dialog button.primary-button').disabled);
    assert.equal(await page.evaluate(()=>state.view),'equipment');assert.equal(await page.evaluate(()=>state.viewRevision),cancelledRevision);assert.equal(await page.evaluate(()=>state.configuration.profile_revision),revision);
    assert.equal(await page.locator('#search-resume').isVisible(),false);assert.equal(requests(),initialRequests+1);
    assert.equal(await snapshot(),protectedBefore);assert.equal(JSON.stringify(inventory.fixtureA),originalInventory);
    cases.push({mounting,width,late_reply_does_not_navigate:true,no_automatic_search:true,counters_unchanged:true});continue;
   }
   await save.click();await page.waitForFunction(expected=>state.view===expected,ordinary?'projects':'availability');
   assert.equal(await dialog.isVisible(),false);assert.equal(await snapshot(),protectedBefore);
   assert.equal(JSON.stringify(inventory.fixtureA),originalInventory);assert.equal(inventory.fixtureB.slots.length,mounting==='single'?1:mounting==='wheel'?2:0);
   if(ordinary){
    assert.equal(requests(),initialRequests);assert.equal(await page.locator('#projects-step').isVisible(),true);
    assert.equal(await page.evaluate(()=>state.refusedSearchResume),null);
    cases.push({mounting,width,ordinary_configuration_path_preserved:true,no_automatic_search:true,counters_unchanged:true});continue;
   }
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
   response=structuredClone(mounting==='none'?refused:base);await page.locator('#request-recommendation').click();await page.waitForFunction(()=>!state.requestingRecommendation);
   assert.equal(requests(),initialRequests+2);assert.equal(await snapshot(),protectedBefore);
   const segment=writes.slice(start);assert.equal(segment.length,4);assert.equal(segment.filter(w=>w.path==='/v1/configuration').length,1);assert.equal(segment.filter(w=>w.path==='/v1/filter-inventory').length,1);
   cases.push({mounting,width,targeted,saveLabel:expectedLabel,direct_return:true,complete_wizard_clicked:true,target_equipment_correct:true,old_equipment_inventory_unchanged:true,hours_and_20_5_preserved:true,no_automatic_search:true,weather_link_keyboard_and_pointer:true,live_label_simple_and_pro:true,counters_unchanged:true});
  }
  assert.deepEqual(errors,[]);assert.deepEqual(dialogs,[]);
  if(out)fs.writeFileSync(path.join(out,'verification.json'),JSON.stringify({success:true,source_base:'5e2cf1202df0cc60d695ce5a91ebde918c48d474',cases,writes,errors,dialogs,http_intercepted:true,no_personal_profile:true},null,2));
  console.log('PASS: 13 scenarios, including 4 stale GET cases blocked and 2 concurrent saves rejected, explicit reload/review, 5 direct returns, ordinary configuration and cancelled late reply; actual optics/camera/filter save, selected project or comparison, 20/5 and counters preserved, no automatic search');
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
