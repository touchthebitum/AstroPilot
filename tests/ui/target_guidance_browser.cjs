// Pass a JSON export of project_templates() as argv[2]. No live API or profile.
const {timeHeaders,timeData}=require('./timezone_fixture.cjs');
const {chromium}=require('playwright');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
(async()=>{
 const templates=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));
 const web=path.resolve(__dirname,'../../astropilot/web');
 const browser=await chromium.launch({headless:true,chromiumSandbox:true,
  ...(process.env.NIGHTMERIT_TEST_CHROME?{executablePath:process.env.NIGHTMERIT_TEST_CHROME}:{channel:'chrome'})});
 try {
  const context=await browser.newContext();let writes=0;
  await context.route('http://nightmerit.test/**',route=>{
   const url=new URL(route.request().url());
   if(route.request().method()!=='GET')writes++;
   if(url.pathname==='/ui/timezone-data.js')return route.fulfill({headers:timeHeaders,contentType:'text/javascript',body:timeData});
   if(url.pathname==='/')return route.fulfill({headers:timeHeaders,contentType:'text/html',body:fs.readFileSync(path.join(web,'index.html'),'utf8').replaceAll('__ASTROPILOT_SESSION_TIMING__','').replaceAll('__ASTROPILOT_ASSET_TOKEN__','review')});
   const file={'/ui/timezone-authority.js':'timezone-authority.js','/ui/app.js':'app.js','/ui/styles.css':'styles.css'}[url.pathname];
   if(file)return route.fulfill({headers:timeHeaders,contentType:file.endsWith('.js')?'text/javascript':'text/css',body:fs.readFileSync(path.join(web,file),'utf8')});
   return route.fulfill({headers:timeHeaders,status:503,contentType:'application/json',body:'{}'});
  });
  const page=await context.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto('http://nightmerit.test/');await page.waitForFunction(()=>state.view==='configuration_error');
  await page.evaluate(templates=>{
   state.configuration={configured:false,projects:{}};
   state.configurationDraft={site:null,equipment:{preset_id:'samyang_183'},projects:{}};
   state.projectTemplates=templates;renderProjects();setView('projects');
   const select=document.querySelector('#project-template');
   select.replaceChildren(new Option(templates[0].display_name,templates[0].catalog_key));
   document.querySelector('#project-create').open=true;
   document.querySelector('#project-create-fields').hidden=false;
   renderNewProjectIntents();
  },templates);
  const ha=page.locator('[data-new-intent-id="sh2-129_ha"]'),oxygen=page.locator('[data-new-intent-id="ou4_oiii"]');
  assert.match(await page.locator('#project-target-guidance').innerText(),/Sh2-129 en Hα/);
  assert.match(await ha.innerText(),/hydrogène/);assert.match(await oxygen.innerText(),/Très difficile/);
  assert.equal(await ha.locator('input[type=checkbox]').isChecked(),false);
  assert.equal(await oxygen.locator('input[type=checkbox]').isChecked(),false);
  assert.equal(await ha.locator('[data-target-hours]').inputValue(),'');
  for(const mode of ['simple','pro'])for(const width of [390,1280]){
   await page.evaluate(mode=>applyUiMode(mode),mode);await page.setViewportSize({width,height:950});
   await oxygen.locator('summary').focus();await page.keyboard.press('Enter');
   assert.equal(await oxygen.locator('details').evaluate(e=>e.open),true);
   assert.match(await oxygen.locator('details').innerText(),/ne dispose pas encore d’une estimation fiable/);
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
   if(mode==='simple'&&width===1280&&process.env.NIGHTMERIT_TEST_SCREENSHOT)await page.screenshot({path:process.env.NIGHTMERIT_TEST_SCREENSHOT,fullPage:true});
   await oxygen.locator('summary').click();
  }
  await ha.locator('input[type=checkbox]').check();await ha.locator('[data-target-hours]').fill('10');
  await oxygen.locator('summary').click();await page.locator('#ui-mode').selectOption('pro');await page.locator('#ui-mode').selectOption('simple');
  assert.equal(await ha.locator('input[type=checkbox]').isChecked(),true);
  assert.equal(await ha.locator('[data-target-hours]').inputValue(),'10');
  assert.equal(await oxygen.locator('input[type=checkbox]').isChecked(),false);
  assert.equal(await page.evaluate(()=>Object.keys(state.configurationDraft.projects).length),0);
  assert.equal(writes,0,'reading advice must not create, save or credit a project');
  // Explicit no-images consent survives panels and rerenders, scoped to a draft/target.
  await page.locator('#project-new-empty').check();
  for(const mode of ['simple','pro']){
   await page.evaluate(mode=>{applyUiMode(mode);setView('availability');setView('projects');renderNewProjectIntents();},mode);
   assert.equal(await page.locator('#project-new-empty').isChecked(),true);
   assert.equal(await ha.locator('input[type=checkbox]').isChecked(),false,'start state is not filter ownership');
  }
  await page.evaluate(()=>{
   const select=document.querySelector('#project-template'),second=state.projectTemplates[1];
   select.append(new Option(second.display_name,second.catalog_key));select.value=second.catalog_key;renderNewProjectIntents();
  });
  assert.equal(await page.locator('#project-new-empty').isChecked(),false,'no transfer to a different target');
  await page.evaluate(()=>{document.querySelector('#project-template').value=state.projectTemplates[0].catalog_key;renderNewProjectIntents();});
  assert.equal(await page.locator('#project-new-empty').isChecked(),true);
  await page.locator('#project-new-empty').uncheck();
  await page.evaluate(()=>renderNewProjectIntents());
  assert.equal(await page.locator('#project-new-empty').isChecked(),false,'withdrawal is preserved');
  await page.locator('#project-new-empty').check();
  await page.evaluate(()=>{state.configurationDraft=structuredClone(state.configurationDraft);renderNewProjectIntents();});
  assert.equal(await page.locator('#project-new-empty').isChecked(),false,'no consent carried to a new draft');
  assert.equal(writes,0,'restoring consent must not write or credit a project');
  // Unsupported equipment must not become compatible merely because advice exists.
  await page.evaluate(()=>{state.configurationDraft.equipment={custom:{camera_model:'unknown'}};renderNewProjectIntents();});
  assert.equal(await ha.locator('input[type=checkbox]').isDisabled(),true);
  assert.equal(await oxygen.locator('input[type=checkbox]').isDisabled(),true);
  // Missing editorial data must clear old guidance and leave the form usable.
  await page.evaluate(()=>{delete state.projectTemplates[0].guidance;for(const intent of state.projectTemplates[0].acquisition_intents)delete intent.guidance;renderNewProjectIntents();});
  assert.equal(await page.locator('#project-target-guidance').isVisible(),false);
  assert.equal(await page.locator('.target-choice-help').count(),0);
  assert.deepEqual(errors,[]);
  console.log('PASS: contextual advice, keyboard disclosures, Simple/Pro 390/1280px, no automatic goals/filter consent/writes, incompatible equipment, missing guidance and scoped no-images consent.');
 } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
