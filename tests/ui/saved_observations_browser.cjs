// Isolated browser fixtures: no real profile, forecast, observation write or credit.
const {timeHeaders,timeData}=require('./timezone_fixture.cjs');
const {chromium}=require('playwright');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
(async()=>{
 const web=path.resolve(__dirname,'../../astropilot/web');
 const browser=await chromium.launch({headless:true,chromiumSandbox:true,
  ...(process.env.NIGHTMERIT_TEST_CHROME?{executablePath:process.env.NIGHTMERIT_TEST_CHROME}:{channel:'chrome'})});
 try {
  const context=await browser.newContext();const traffic=[],errors=[];
  const report=(id,d,time)=>({observation_id:id,decision_id:d,execution_id:null,observed_at_utc:time,
   supersedes_observation_id:null,conditions:{cloud_state:'overcast',surface_condition:'dew_present'}});
  const first=report('a','d','2026-10-22T19:03:00Z'),older=report('b','old','2026-10-21T19:00:00Z');
  await context.route('http://nightmerit.test/**',route=>{
   const req=route.request(),url=new URL(req.url());traffic.push([req.method(),url.pathname]);
   const json=(body,status=200)=>route.fulfill({headers:timeHeaders,status,contentType:'application/json',body:JSON.stringify(body)});
   if(url.pathname==='/ui/timezone-data.js')return route.fulfill({headers:timeHeaders,contentType:'text/javascript',body:timeData});
   if(url.pathname==='/')return route.fulfill({headers:timeHeaders,contentType:'text/html',body:fs.readFileSync(path.join(web,'index.html'),'utf8').replaceAll('__ASTROPILOT_SESSION_TIMING__','').replaceAll('__ASTROPILOT_ASSET_TOKEN__','test')});
   const file={'/ui/timezone-authority.js':'timezone-authority.js','/ui/app.js':'app.js','/ui/styles.css':'styles.css'}[url.pathname];
   if(file)return route.fulfill({headers:timeHeaders,contentType:file.endsWith('.js')?'text/javascript':'text/css',body:fs.readFileSync(path.join(web,file),'utf8')});
   if(url.pathname==='/v1/field-observations')return json({items:[{observation:url.searchParams.has('before')?older:first,context:{site_name:'Buttes',latitude:46.9,longitude:6.5,timezone:'Europe/Zurich'}}],next_before:url.searchParams.has('before')?null:'a'});
   if(url.pathname==='/v1/decisions/d/field-observations')return json([first,{...first,observation_id:'another-execution',execution_id:'exec'}]);
   if(url.pathname==='/v1/decisions/old/field-observations')return json([older]);
   if(url.pathname==='/v1/field-observations/a/outcome-evaluation')return json({observation_id:'a',decision_id:'d',execution_id:null,evaluation_id:'evaluation',version:'outcome_evaluation.v1',comparison_id:'comparison',computed_at_utc:'2026-10-22T19:06:00Z',status:'not_comparable',results:[],reasons:[{code:'forecast_outside_temporal_tolerance',variable:null}],assessment:null,evidence_reference:null});
   if(url.pathname==='/v1/field-observations/b/outcome-evaluation')return json({detail:{code:'outcome_evaluation_not_found'}},404);
   return json({},503);
  });
  const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));
  await page.goto('http://nightmerit.test/');await page.waitForFunction(()=>state.view==='configuration_error');
  await page.evaluate(()=>{
   localStorage.clear();state.configuration={configured:true,site:{name:'Buttes',latitude:46.9,longitude:6.5,timezone:'Europe/Zurich'},projects:{}};
   state.configurationDraft={site:state.configuration.site,equipment:{preset_id:'samyang_183'},projects:{}};
   setView('discovery');
  });
  for(const mode of ['simple','pro'])for(const width of [390,1280]){
   await page.setViewportSize({width,height:1000});await page.evaluate(mode=>applyUiMode(mode),mode);
   assert.equal(await page.locator('#saved-observations-open').isVisible(),true,'entry available even with no target result');
   await page.locator('#saved-observations-open').click();
   await page.locator('.saved-observation-card').first().waitFor();
   assert.match(await page.locator('.saved-observation-card').first().innerText(),/22 octobre 2026.*21:03.*UTC\+2/);
   assert.match(await page.locator('.saved-observation-card').first().innerText(),/Buttes/);
   await page.locator('#saved-observations-more').click();
   await page.waitForFunction(()=>document.querySelectorAll('.saved-observation-card').length===2);
   await page.locator('.saved-observation-card button').first().click();
   await page.waitForFunction(()=>document.querySelector('#outcome-result').textContent.includes('trop éloignée'));
   assert.equal(await page.locator('#field-observation-form').isVisible(),false);
   assert.equal(await page.locator('#observation-save').isVisible(),false);
   assert.equal(await page.locator('#saved-observation-details').isVisible(),true);
   assert.equal(await page.locator('.observation-entry-heading').isVisible(),false);
   assert.match(await page.locator('#saved-observation-details').innerText(),/Nuages : Couvert/);
   assert.match(await page.locator('#saved-observation-details').innerText(),/Surface : Rosée/);
   assert.match(await page.locator('#observation-time-summary').innerText(),/22 octobre 2026.*21:03/);
   if(mode==='simple')assert.doesNotMatch(await page.locator('#outcome-observation').innerText(),/2026-10-22T|another-execution/);
   assert.equal(await page.locator('#field-observation-dialog').evaluate(e=>e.scrollWidth<=e.clientWidth),true);
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
   if(mode==='simple'&&width===1280&&process.env.NIGHTMERIT_TEST_SCREENSHOT)await page.screenshot({path:process.env.NIGHTMERIT_TEST_SCREENSHOT,fullPage:true});
   await page.locator('#saved-observation-back').click();
   await page.locator('.saved-observation-card').first().waitFor();
   await page.locator('#saved-observations-close').click();
  }
  await page.locator('#saved-observations-open').click();await page.locator('.saved-observation-card').waitFor();
  await page.locator('#saved-observations-more').click();await page.waitForFunction(()=>document.querySelectorAll('.saved-observation-card').length===2);
  await page.locator('.saved-observation-card button').nth(1).click();
  await page.waitForFunction(()=>document.querySelector('#outcome-result').textContent.includes('Aucune comparaison'));
  assert.equal(await page.locator('#outcome-compare').isEnabled(),true,'creation still requires its separate explicit action');
  assert.equal(traffic.some(([method])=>method!=='GET'),false,'consultation creates no comparison, observation, session or credit');
  assert.equal(traffic.some(([,url])=>/tonight|target-suggestions/.test(url)),false,'no forecast or target search required');
  assert.deepEqual(errors,[]);
  console.log('PASS: direct saved report access without localStorage, paging, local dates, Simple/Pro 390/1280px, read-only details, exact execution context, canonical GET only, missing comparison not created.');
 } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1});
