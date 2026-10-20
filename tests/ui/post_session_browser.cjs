// argv[2]: isolated configuration/progress fixture exported from the real API.
const {timeHeaders,timeData}=require('./timezone_fixture.cjs');
const {chromium}=require('playwright');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
(async()=>{
 const fixture=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));
 const web=path.resolve(__dirname,'../../astropilot/web');let writes=[];
 const browser=await chromium.launch({headless:true,chromiumSandbox:true,
  ...(process.env.NIGHTMERIT_TEST_CHROME?{executablePath:process.env.NIGHTMERIT_TEST_CHROME}:{channel:'chrome'})});
 try {
  const context=await browser.newContext();
  await context.route('http://nightmerit.test/**',route=>{
   const url=new URL(route.request().url()),method=route.request().method();
   if(method!=='GET')writes.push({path:url.pathname,body:route.request().postDataJSON()});
   if(url.pathname==='/ui/timezone-data.js')return route.fulfill({headers:timeHeaders,contentType:'text/javascript',body:timeData});
   if(url.pathname==='/')return route.fulfill({headers:timeHeaders,contentType:'text/html',body:fs.readFileSync(path.join(web,'index.html'),'utf8').replaceAll('__ASTROPILOT_SESSION_TIMING__','').replaceAll('__ASTROPILOT_ASSET_TOKEN__','review')});
   const file={'/ui/timezone-authority.js':'timezone-authority.js','/ui/app.js':'app.js','/ui/styles.css':'styles.css'}[url.pathname];
   if(file)return route.fulfill({headers:timeHeaders,contentType:file.endsWith('.js')?'text/javascript':'text/css',body:fs.readFileSync(path.join(web,file),'utf8')});
   if(url.pathname==='/v1/projects/Sh2-129/progress')return route.fulfill({headers:timeHeaders,contentType:'application/json',body:JSON.stringify(fixture.progress)});
   return route.fulfill({headers:timeHeaders,status:503,contentType:'application/json',body:'{}'});
  });
  const page=await context.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto('http://nightmerit.test/');await page.waitForFunction(()=>state.view==='configuration_error');
  await page.evaluate(configuration=>{
   state.configuration=configuration;state.configurationDraft=draftFromConfiguration(configuration);
   renderProjects();setView('projects');
   state.acceptedMission={mission_id:'retained-mission'};
   ui.savedMissionEntry.hidden=false;
   ui.savedMissionChoice.replaceChildren(new Option('Mission synthétique conservée','retained-mission'));
  },fixture.configuration);
  await page.locator('.simple-project-card summary').click();
  await page.getByRole('button',{name:'Retrouver mes sessions NightMerit',exact:true}).click();
  assert.equal(await page.evaluate(()=>state.view),'availability');
  await page.waitForFunction(()=>document.querySelector('#saved-mission-choice')===document.activeElement);
  assert.equal(await page.evaluate(()=>state.acceptedMission.mission_id),'retained-mission');
  assert.equal(writes.length,0,'navigation must not create a session or credit');
  await page.evaluate(()=>navigateGuidedProjects());
  await page.getByRole('button',{name:'Modifier mon projet',exact:true}).click();
  const section=page.locator('#project-intents [data-intent-id="sh2-129_ha"]');
  await section.waitFor();
  for(const mode of ['simple','pro'])for(const width of [390,1280]){
   await page.evaluate(mode=>applyUiMode(mode),mode);await page.setViewportSize({width,height:950});
   await section.locator('[data-field="acquired_frames"]').fill('');
   await page.getByRole('button',{name:'Enregistrer les modifications',exact:true}).click();
   assert.equal(await page.locator('.project-progress-feedback').innerText(),'Indiquez le nombre de poses déjà réalisées. Si vous n’avez pas encore commencé, saisissez 0.');
   assert.equal(await section.locator('[data-field="acquired_frames"]').inputValue(),'');
   assert.equal(writes.length,0,'unknown is not an implicit zero');
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
   if(mode==='simple'&&width===1280&&process.env.NIGHTMERIT_TEST_SCREENSHOT)await page.screenshot({path:process.env.NIGHTMERIT_TEST_SCREENSHOT,fullPage:true});
  }
  await section.locator('[data-field="acquired_frames"]').fill('0');
  await section.locator('[data-field="exposure_seconds"]').fill('');
  await page.getByRole('button',{name:'Enregistrer les modifications',exact:true}).click();
  assert.match(await page.locator('.project-progress-feedback').innerText(),/durée d’une pose/);
  assert.equal(writes.length,0);
  await section.locator('[data-field="exposure_seconds"]').fill('300');
  await page.getByRole('button',{name:'Enregistrer les modifications',exact:true}).click();
  await page.waitForFunction(()=>document.querySelector('.project-progress-feedback').textContent.includes('enregistrées'));
  assert.equal(writes.length,1);
  assert.equal(writes[0].body.acquisition_intent_progress[0].acquired_frames,0);
  assert.equal(writes[0].body.acquisition_intent_targets[0].target_hours,2);
  await page.evaluate(()=>{
   state.sessions=[{execution:{execution_id:'session-test',status:'completed',actual_start:null},acquisition_intent_id:'sh2-129_ha',evidence:[],credit:null,historical_baseline_seconds:0,historical_baseline_confirmed:true,acquired_before_seconds:0,session_credit_seconds:0,acquired_after_seconds:0,current_acquired_seconds:0,target_hours:2,remaining_hours:2}];
   state.activeSessionId='session-test';renderSession();ui.mission.showModal();
  });
  for(const mode of ['simple','pro'])for(const width of [390,1280]){
   await page.evaluate(mode=>applyUiMode(mode),mode);await page.setViewportSize({width,height:950});
   for(const stage of ['in_progress','completed','evidence','credited','interrupted','unconfirmed']){
    await page.evaluate(stage=>{
     const s=state.sessions[0];s.execution.status=['evidence','credited'].includes(stage)?'completed':stage;
     s.evidence=['evidence','credited'].includes(stage)?[{category:'acquisition',usable_integration_duration:1800}]:[];
     s.credit=stage==='credited'?{execution_id:'session-test'}:null;renderSession();
    },stage);
    const message=await page.locator('#session-next-step').textContent();
    assert.match(message,{'in_progress':/terminez la session/,'completed':/Session terminée/,'evidence':/pas encore ajoutée/,'credited':/déjà été ajoutée/,'interrupted':/aucun temps/,'unconfirmed':/vérifié/}[stage]);
    assert.equal(await page.locator('#session-next-step').isVisible(),mode==='simple');
    if(stage==='credited'||stage==='interrupted')assert.equal(await page.locator('#session-apply-credit').isVisible(),false);
    assert.equal(await page.locator('#mission-dialog').evaluate(el=>el.scrollWidth<=el.clientWidth),true);
   }
  }
  assert.equal(writes.length,1,'reading stage guidance must not issue mutations');
  assert.deepEqual(errors,[]);
  console.log('PASS: saved-session navigation, explicit zero vs unknown, distinct exposure error, retained goal, stage advice, no implicit writes, Simple/Pro 390/1280px.');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
