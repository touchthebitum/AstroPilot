// Real production DOM with the production empty-configuration catalogue; no user profile.
const {timeHeaders,timeData}=require('./timezone_fixture.cjs');
const {chromium}=require('playwright');
const fs=require('node:fs'),path=require('node:path'),cp=require('node:child_process'),assert=require('node:assert/strict');
(async()=>{
 const root=path.resolve(__dirname,'../..'),web=path.join(root,'astropilot/web');
 const configuration=JSON.parse(cp.execFileSync(process.env.PYTHON_BINARY||'python',['-c',
  'import tempfile,os,json\nfrom pathlib import Path\nwith tempfile.TemporaryDirectory() as t:\n os.environ["ASTROPILOT_DATA_DIR"]=str(Path(t).resolve()/"empty")\n from fastapi.testclient import TestClient\n from astropilot.app import create_app\n print(json.dumps(TestClient(create_app()).get("/v1/configuration").json()))'],{cwd:root,env:{...process.env,PYTHONPATH:root},encoding:'utf8'}));
 const browser=await chromium.launch({headless:true,chromiumSandbox:true,args:['--use-mock-keychain'],...(process.env.CHROME_BINARY?{executablePath:process.env.CHROME_BINARY}:{channel:'chrome'})});
 try{
  const context=await browser.newContext();const traffic=[],errors=[];
  const references=JSON.parse(fs.readFileSync(path.join(root,'astropilot/catalogue_data/equipment_references_v1.json'),'utf8'));
  for(const entry of references.entries)entry.can_copy=entry.category!=='filter'&&entry.id!=='skywatcher_quattro_200';
  let referenceCalls=0;
  await context.route('http://nightmerit.test/**',async route=>{
   const req=route.request(),url=new URL(req.url());traffic.push([req.method(),url.pathname]);
   const respond=(body,status=200)=>route.fulfill({headers:timeHeaders,status,contentType:'application/json',body:JSON.stringify(body)});
   if(url.pathname==='/v1/configuration')return respond(configuration);
   if(url.pathname==='/v1/equipment-references'){
    referenceCalls++;
    if(referenceCalls===1)return respond({},503);
    await new Promise(resolve=>setTimeout(resolve,150));
    return respond(references);
   }
   if(url.pathname==='/ui/timezone-data.js')return route.fulfill({headers:timeHeaders,contentType:'text/javascript',body:timeData});
   if(url.pathname==='/')return route.fulfill({headers:timeHeaders,contentType:'text/html',body:fs.readFileSync(path.join(web,'index.html'),'utf8').replaceAll('__ASTROPILOT_SESSION_TIMING__','')});
   const file={'/ui/app.js':'app.js','/ui/styles.css':'styles.css','/ui/timezone-authority.js':'timezone-authority.js'}[url.pathname];
   if(file)return route.fulfill({headers:timeHeaders,contentType:file.endsWith('.css')?'text/css':'text/javascript',body:fs.readFileSync(path.join(web,file),'utf8')});
   return respond({},503);
  });
  const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));await page.goto('http://nightmerit.test/');await page.locator('#site-next').waitFor();
  await page.locator('details:has(#site-latitude)').evaluate(e=>e.open=true);
  await page.locator('#site-latitude').fill('46.75');await page.locator('#site-longitude').fill('6.55');await page.locator('#site-bortle').fill('4');await page.locator('#site-next').click();
  assert.equal(await page.locator('input[name="preset-equipment"]:checked').count(),0);
  await page.locator('#equipment-next').click();assert.match(await page.locator('#configuration-form-error').textContent(),/Choisissez/);
  await page.locator('#equipment-search').fill('zwo 183');assert.equal(await page.locator('.equipment-choice:visible').count(),1);await page.locator('input[name="preset-equipment"][value="samyang_183"]').check();
  await page.locator('#equipment-next').click();assert.equal(await page.evaluate(()=>state.configurationDraft.equipment.preset_id),'samyang_183');
  await page.locator('#projects-step [data-back="equipment"]').click();
  const draft=await page.evaluate(()=>JSON.stringify(state.configurationDraft));
  await page.locator('#equipment-search').fill('caméra inconnue <img src=x onerror=alert(1)>');assert.equal(await page.locator('#equipment-no-results').isVisible(),true);assert.equal(await page.locator('#equipment-search-panel img').count(),0);
  await page.locator('#equipment-next').click();assert.equal(await page.locator('#equipment-step').isVisible(),true);assert.equal(await page.evaluate(()=>JSON.stringify(state.configurationDraft)),draft);
  // Separate components: failure/retry, current query after a delayed response, exact variants.
  await page.locator('input[name="equipment-kind"][value="preset"]').check();
  await page.locator('#equipment-search').fill('Newton');await page.locator('#equipment-find-component').click();
  await page.locator('#equipment-reference-retry').waitFor();assert.equal(await page.evaluate(()=>JSON.stringify(state.configurationDraft)),draft);
  await page.locator('#equipment-reference-retry').click();await page.locator('#equipment-reference-query').fill('Quattro 150');
  await page.waitForFunction(()=>document.querySelectorAll('.equipment-reference-card').length===2);
  assert.equal(await page.locator('#equipment-reference-query').inputValue(),'Quattro 150');
  await page.locator('#equipment-reference-query').fill('Newton');assert.equal(await page.locator('.equipment-reference-card').count(),5);
  assert.match(await page.locator('#equipment-reference-status').textContent(),/Newton désigne un type/);
  await page.locator('#equipment-reference-query').fill('Skywatcher Quattro');assert.equal(await page.locator('.equipment-reference-card').count(),5);
  await page.locator('#equipment-reference-query').fill('Newton');
  const ambiguous=page.locator('[data-reference-id="skywatcher_quattro_200"]');await ambiguous.locator('summary').click();assert.equal(await ambiguous.locator('button').count(),0);
  const native=page.locator('[data-reference-id="skywatcher_quattro_150_native"]');await native.locator('summary').click();
  assert.equal(await native.locator('button').isDisabled(),true);
  await page.locator('input[name="equipment-kind"][value="custom"]').check();
  await page.locator('#custom-camera-model').fill('Ma caméra à conserver');
  await native.locator('input').check();await native.locator('button').click();
  assert.equal(await page.locator('#custom-focal-length-mm').inputValue(),'600');assert.equal(await page.locator('#custom-camera-model').inputValue(),'Ma caméra à conserver');
  assert.equal(await page.locator('input[name="equipment-kind"][value="custom"]').isChecked(),true);
  assert.equal(await page.evaluate(()=>JSON.stringify(state.configurationDraft)),draft);
  const reduced=page.locator('[data-reference-id="skywatcher_quattro_150_reduced"]');await reduced.locator('summary').click();await reduced.locator('input').check();await reduced.locator('button').click();
  assert.equal(await page.locator('#custom-focal-length-mm').inputValue(),'518');assert.equal(await page.locator('#custom-f-ratio').inputValue(),'3.45');assert.match(await page.locator('#custom-optics-model').inputValue(),/correcteur/);
  const optics=await page.locator('#custom-optics-model').inputValue();
  await page.locator('#equipment-reference-category').selectOption('camera');await page.locator('#equipment-reference-query').fill('ASI183');
  assert.equal(await page.locator('.equipment-reference-card').count(),2);
  const colour=page.locator('[data-reference-id="zwo_asi183mc_pro"]');await colour.locator('summary').click();await colour.locator('input').check();await colour.locator('button').click();
  assert.equal(await page.locator('#custom-monochrome').isChecked(),false);assert.equal(await page.locator('#custom-optics-model').inputValue(),optics);
  const mono=page.locator('[data-reference-id="zwo_asi183mm_pro"]');await mono.locator('summary').click();await mono.locator('input').check();await mono.locator('button').click();
  assert.equal(await page.locator('#custom-monochrome').isChecked(),true);
  assert.equal(await page.evaluate(()=>readEquipment()[0].custom.sensor_width_px),5496);
  assert.equal(await page.evaluate(()=>JSON.stringify(state.configurationDraft)),draft);
  await page.locator('#equipment-reference-category').selectOption('filter');await page.locator('#equipment-reference-query').fill('LRGB');
  assert.equal(await page.locator('.equipment-reference-card').count(),2);assert.equal(await page.locator('#equipment-reference-results input').count(),0);assert.equal(await page.locator('#equipment-reference-results button').count(),0);
  await page.locator('#equipment-reference-query').fill('inconnu <img src=x onerror=alert(1)>');assert.equal(await page.locator('.equipment-reference-card').count(),0);assert.equal(await page.locator('#equipment-reference-results img').count(),0);
  assert.match(await page.locator('#equipment-reference-status').textContent(),/saisie manuelle/);
  for(const mode of ['simple','pro'])for(const width of [390,1280]){
   await page.evaluate(m=>applyUiMode(m),mode);await page.setViewportSize({width,height:1000});await page.locator('#equipment-reference-category').selectOption('optics');await page.locator('#equipment-reference-query').fill('Newton');
   await page.locator('[data-reference-id="skywatcher_quattro_150_native"] summary').click();assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
   if(mode==='simple'&&width===1280&&process.env.REFERENCE_SCREENSHOT)await page.screenshot({path:process.env.REFERENCE_SCREENSHOT,fullPage:true});
  }
  assert.equal(referenceCalls,2);
  await page.locator('input[name="equipment-kind"][value="preset"]').check();
  await page.locator('#equipment-clear-search').click();assert.equal(await page.locator('.equipment-choice:visible').count(),configuration.preset_equipment.length);assert.equal(await page.locator('input[value="samyang_183"]').isChecked(),true);
  // Existing saved selection survives prefill and Simple/Pro changes; searching never writes.
  await page.evaluate(()=>prefillConfiguration());assert.equal(await page.locator('input[value="samyang_183"]').isChecked(),true);
  for(const mode of ['simple','pro'])for(const width of [390,1280]){
   await page.evaluate(m=>applyUiMode(m),mode);await page.setViewportSize({width,height:1000});await page.locator('#equipment-search').fill('ASI 2600');assert.equal(await page.locator('.equipment-choice:visible').count(),2);assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
   if(mode==='simple'&&width===1280&&process.env.EQUIPMENT_SCREENSHOT){await page.locator('#equipment-search').fill('');await page.screenshot({path:process.env.EQUIPMENT_SCREENSHOT,fullPage:true});}
  }
  await page.locator('#equipment-search').fill('inconnu');await page.locator('#equipment-enter-custom').click();assert.equal(await page.locator('#custom-equipment').isVisible(),true);assert.equal(await page.locator('#custom-optics-manufacturer').inputValue(),'');
  await page.locator('#equipment-next').click();assert.equal(await page.locator('#equipment-step').isVisible(),true);assert.equal(await page.evaluate(()=>JSON.stringify(state.configurationDraft)),draft);
  // A custom setup stays custom; a catalogue miss must not replace it with a preset.
  await page.evaluate(()=>{state.configurationDraft.equipment={custom:{optics_manufacturer:'Personnel',optics_model:'Mon modèle',focal_length_mm:300,aperture_mm:60,f_ratio:5,camera_manufacturer:'Personnel',camera_model:'Caméra',pixel_size_um:3.76,sensor_width_px:3008,sensor_height_px:3008,monochrome:true}};prefillConfiguration();});
  assert.equal(await page.locator('input[name="equipment-kind"][value="custom"]').isChecked(),true);assert.equal(await page.locator('#custom-optics-model').inputValue(),'Mon modèle');
  await page.evaluate(()=>{window.readCustom=readEquipment();applyUiMode('simple');});assert.equal(await page.evaluate(()=>readEquipment()[0].custom.optics_model),'Mon modèle');
  // Exact filter references remain an explicit, unchecked choice.
  await page.evaluate(()=>{state.configurationDraft.equipment={preset_id:'samyang_183'};state.projectTemplates=[{catalog_key:'M42',display_name:'M42',imaging_field_id:'m42',acquisition_intents:[{acquisition_intent_id:'m42_ha',label:'Hα',supported_filters:[{equipment_id:'samyang_183',label:'Référence synthétique',filter_profile_id:'synthetic-ha',fwhm_nm:6.5}]}]}];document.querySelector('#project-template').replaceChildren(new Option('M42','M42'));renderNewProjectIntents();});
  assert.equal(await page.locator('#project-new-intents input[type="checkbox"]').isChecked(),false);
  await page.evaluate(()=>{state.configurationDraft.equipment={custom:{optics_model:'Mon modèle'}};renderNewProjectIntents();});assert.equal(await page.locator('#project-new-intents input[type="checkbox"]').isDisabled(),true);
  assert(traffic.every(([m])=>m==='GET'));assert.deepEqual(errors,[]);console.log(JSON.stringify({result:'PASS',search:true,unknown_and_custom:true,no_default_preset:true,retained_choices:true,no_filter_auto_confirmation:true,component_variants:true,partial_copy:true,reference_failure_retry:true,late_response_current_query:true,simple_pro:[390,1280],read_only:true}));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1)});
