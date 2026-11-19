// Presentation regression with intercepted API only: no server or user profile.
const {chromium}=require('playwright');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {timeHeaders,timeData}=require('./timezone_fixture.cjs');
(async()=>{
 const web=path.resolve(__dirname,'../../astropilot/web'),out=process.env.NIGHTMERIT_PROOF_DIR;
 const browser=await chromium.launch({headless:true,executablePath:process.env.NIGHTMERIT_TEST_CHROME});
 try {
  const page=await browser.newPage(),errors=[],requests=[],cases=[];let pending=null;
  page.on('pageerror',e=>errors.push(e.message));
  await page.route('http://127.0.0.1:18483/**',async route=>{
   const url=new URL(route.request().url());
   if(route.request().method()==='PUT'){
    assert.equal(url.pathname,'/v1/projects/M42/progress');assert.ok(pending);
    const body=route.request().postDataJSON();requests.push(body);pending.started();await pending.gate;
    if(pending.status==='network')return route.abort('failed');
    return route.fulfill({headers:timeHeaders,status:pending.status,json:pending.status===200?{...pending.progress,profile_revision:body.expected_revision+1,acquisition_intent_progress:body.acquisition_intent_progress,acquisition_intent_targets:body.acquisition_intent_targets}:{detail:{code:'profile_revision_conflict'}}});
   }
   if(url.pathname==='/')return route.fulfill({headers:timeHeaders,contentType:'text/html',body:fs.readFileSync(path.join(web,'index.html'),'utf8').replaceAll('__ASTROPILOT_ASSET_TOKEN__','review').replaceAll('__ASTROPILOT_SESSION_TIMING__','')});
   if(url.pathname==='/ui/timezone-data.js')return route.fulfill({headers:timeHeaders,contentType:'text/javascript',body:timeData});
   const file={'/ui/app.js':'app.js','/ui/styles.css':'styles.css','/ui/timezone-authority.js':'timezone-authority.js'}[url.pathname];
   return file?route.fulfill({headers:timeHeaders,contentType:file.endsWith('.css')?'text/css':'text/javascript',body:fs.readFileSync(path.join(web,file),'utf8')}):route.fulfill({headers:timeHeaders,status:503,json:{}});
  });
  await page.goto('http://127.0.0.1:18483/');await page.waitForFunction(()=>typeof state!=='undefined'&&state.view==='configuration_error');
  const progress={project_id:'M42',profile_revision:1,imaging_field_id:'m42',imaging_fields:[{imaging_field_id:'m42',display_name:'M42',acquisition_intents:[{acquisition_intent_id:'m42_ha',filter_type:'Ha'}]}],acquisition_intent_progress:[{acquisition_intent_id:'m42_ha',acquired_duration_manual:0}],acquisition_intent_targets:[{acquisition_intent_id:'m42_ha',target_hours:15}],intent_progress_breakdown:[]};
  const inspect=()=>page.locator('.project-progress-feedback').evaluate(el=>({text:el.textContent,error:el.classList.contains('error'),success:el.classList.contains('confirmation-success'),background:getComputedStyle(el).backgroundColor,icon:getComputedStyle(el,'::before').content,fits:el.scrollWidth<=el.clientWidth}));
  for(const mode of ['simple','pro'])for(const width of [390,768,1280,1600]){
   await page.setViewportSize({width,height:1000});
   await page.evaluate(({mode,data})=>{applyUiMode(mode);state.configuration={configured:true,profile_revision:1,site:{name:'TEST FICTIF',latitude:47,longitude:7,bortle:4,timezone:'Europe/Zurich'},projects:{M42:{imaging_field_id:'m42',acquisition_intent_progress:data.acquisition_intent_progress,acquisition_intent_targets:data.acquisition_intent_targets}}};state.configurationDraft=draftFromConfiguration(state.configuration);setView('projects');state.progressEditor=data;document.querySelector('#project-progress-editor').hidden=false;document.documentElement.dataset.progressOpen='true';renderProjectProgressEditor('Modifications du projet enregistrées.');}, {mode,data:structuredClone(progress)});
   for(const [status,value]of [[200,'16'],[500,'17'],[409,'18'],['network','19'],[200,'20']]){
    await page.locator('[data-intent-id="m42_ha"] [data-field="target_hours"]').fill(value);
    let release,started;pending={status,progress,gate:new Promise(r=>release=r),started:null};const start=new Promise(r=>started=r);pending.started=started;
    const count=requests.length;await page.evaluate(()=>{void saveProjectProgress()});await start;
    const waiting=await inspect();assert.equal(waiting.text,'Enregistrement des modifications en cours…');assert.equal(waiting.error,false);assert.equal(waiting.success,false);assert.equal(waiting.background,'rgb(19, 44, 64)');assert.ok(waiting.icon.includes('i'));assert.ok(waiting.fits);
    assert.equal(await page.locator('[data-field="target_hours"]').isDisabled(),true);
    await page.evaluate(()=>{void saveProjectProgress()});assert.equal(requests.length,count+1,'second submission while pending must do nothing');
    if(out&&mode==='simple'&&width===390){await page.locator('.project-progress-feedback').scrollIntoViewIfNeeded();await page.screenshot({path:path.join(out,`pending-${status}.png`)});}
    release();await page.waitForFunction(()=>!state.savingProjectProgress);const settled=await inspect();
    assert.equal(settled.error,status!==200);assert.equal(settled.success,status===200);assert.equal(settled.background,status===200?'rgb(17, 59, 50)':'rgb(70, 28, 35)');assert.ok(settled.icon.includes(status===200?'✓':'!'));assert.ok(settled.fits);
    if(status===200)assert.equal(settled.text,'Modifications du projet enregistrées.');
    else {assert.doesNotMatch(settled.text,/en cours|enregistrées\./);assert.equal(await page.locator('[data-field="target_hours"]').inputValue(),value,'failed save preserves input');}
    if(out&&mode==='simple'&&width===390)await page.screenshot({path:path.join(out,`settled-${status}.png`)});
    cases.push({mode,width,status,waiting,settled});
   }
   await page.locator('[data-field="target_hours"]').fill('-1');const count=requests.length;await page.evaluate(()=>saveProjectProgress());assert.equal(requests.length,count);const invalid=await inspect();assert.equal(invalid.error,true);assert.equal(invalid.success,false);assert.match(invalid.text,/Corrigez l’objectif/);
  }
  assert.deepEqual(errors,[]);assert.equal(cases.length,40);
  if(out)fs.writeFileSync(path.join(out,'project-progress-feedback.json'),JSON.stringify({result:'PASS',cases,requests:requests.length,http_mocked:true,ui_context_injection:true,personal_profile_used:false,errors},null,2));
  console.log('PASS: 40 save cycles in Simple/Pro at four widths; neutral pending, success, HTTP 500/409, network failure, retry, no duplicate pending PUT, and invalid-input refusal.');
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exit(1)});
