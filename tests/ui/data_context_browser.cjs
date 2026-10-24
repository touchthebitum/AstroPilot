// All records are synthetic. Copy identification must never write or search weather.
const {timeHeaders,timeData}=require('./timezone_fixture.cjs');
const {chromium}=require('playwright');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
(async()=>{
 const web=path.resolve(__dirname,'../../astropilot/web');
 const browser=await chromium.launch({headless:true,chromiumSandbox:true,
  ...(process.env.NIGHTMERIT_TEST_CHROME?{executablePath:process.env.NIGHTMERIT_TEST_CHROME}:{channel:'chrome'})});
 try {
  const context=await browser.newContext();const traffic=[],errors=[];let fixture,status=200,hold=false,release;
  await context.route('http://nightmerit.test/**',async route=>{
   const req=route.request(),url=new URL(req.url());traffic.push([req.method(),url.pathname]);
   const json=(body,code=200)=>route.fulfill({headers:timeHeaders,status:code,contentType:'application/json',body:JSON.stringify(body)});
   if(url.pathname==='/ui/timezone-data.js')return route.fulfill({headers:timeHeaders,contentType:'text/javascript',body:timeData});
   if(url.pathname==='/')return route.fulfill({headers:timeHeaders,contentType:'text/html',body:fs.readFileSync(path.join(web,'index.html'),'utf8').replaceAll('__ASTROPILOT_SESSION_TIMING__','').replaceAll('__ASTROPILOT_ASSET_TOKEN__','test')});
   const file={'/ui/timezone-authority.js':'timezone-authority.js','/ui/app.js':'app.js','/ui/styles.css':'styles.css'}[url.pathname];
   if(file)return route.fulfill({headers:timeHeaders,contentType:file.endsWith('.js')?'text/javascript':'text/css',body:fs.readFileSync(path.join(web,file),'utf8')});
   if(url.pathname==='/v1/data-context'){
    const data=fixture,code=status;if(hold)await new Promise(r=>release=r);
    return json(data,code).catch(()=>{});
   }
   if(url.pathname==='/v1/field-observations')return json({items:[],next_before:null});
   return json({},503);
  });
  const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));
  await page.goto('http://nightmerit.test/');await page.waitForFunction(()=>state.view==='configuration_error');
  assert.ok(!traffic.some(([,url])=>url==='/v1/data-context'),'paths are fetched only on explicit opening');
  for(const mode of ['simple','pro'])for(const width of [390,1280]){
   await page.setViewportSize({width,height:900});await page.evaluate(mode=>applyUiMode(mode),mode);
   fixture={runtime:{version:'1.0.0b8',build:'8843978'},data_directory:width===390?'C:\\NightMeritResults\\profil':'/Copies personnelles été/NightMerit-Beta-Privee-8843978-Mac/DONNEES-BETA/profil',application_executable:'/private test copy/candidate/AstroPilot'};
   // Footer remains available even when configuration cannot be loaded.
   await page.locator('#data-context-footer').click();
   await page.waitForFunction(()=>!document.querySelector('#data-context-details').hidden);
   assert.equal(await page.locator('#data-context-directory').textContent(),fixture.data_directory);
   assert.equal(await page.locator('#data-context-directory img').count(),0,'server text is never HTML');
   assert.match(await page.locator('#data-context-version').innerText(),/8843978/);
   assert.equal(await page.locator('#data-context-dialog').evaluate(e=>e.scrollWidth<=e.clientWidth),true);
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
   if(mode==='simple'&&width===1280&&process.env.NIGHTMERIT_TEST_SCREENSHOT)await page.screenshot({path:process.env.NIGHTMERIT_TEST_SCREENSHOT,fullPage:true});
   await page.locator('#data-context-close').click();assert.equal(await page.locator('#data-context-dialog').isVisible(),false);
  }
  fixture.data_directory='<img src=x onerror=alert(1)>';
  await page.locator('#data-context-footer').click();await page.locator('#data-context-details').waitFor();
  assert.equal(await page.locator('#data-context-directory').textContent(),fixture.data_directory);
  assert.equal(await page.locator('#data-context-directory img').count(),0);
  await page.locator('#data-context-close').click();
  status=503;
  await page.locator('#data-context-footer').click();
  await page.locator('#data-context-retry').waitFor();
  assert.equal(await page.locator('#data-context-details').isVisible(),false);
  assert.equal(await page.locator('#data-context-directory').textContent(),'','no stale path on failure');
  assert.match(await page.locator('#data-context-status').innerText(),/ne signifie pas que vos données sont absentes/);
  status=200;await page.locator('#data-context-retry').click();await page.locator('#data-context-details').waitFor();
  await page.keyboard.press('Escape');assert.equal(await page.locator('#data-context-dialog').isVisible(),false);
  hold=true;await page.locator('#data-context-footer').click();await page.waitForFunction(()=>document.querySelector('#data-context-status').textContent.startsWith('Lecture'));
  while(!release)await page.waitForTimeout(10);
  await page.locator('#data-context-close').click();release();hold=false;await page.waitForTimeout(50);
  assert.equal(await page.locator('#data-context-details').isVisible(),false,'late response does not reopen or populate closed dialog');
  await page.evaluate(()=>{state.configuration={configured:true};setView('availability');});
  await page.locator('#saved-observations-open').click();await page.locator('#saved-observations-data-context').waitFor();
  await page.locator('#saved-observations-data-context').click();await page.locator('#data-context-details').waitFor();
  await page.locator('#data-context-back').click();await page.locator('#saved-observations-status').waitFor();
  assert.equal(await page.locator('#saved-observations-dialog').isVisible(),true);
  assert.ok(traffic.every(([method])=>method==='GET'));
  assert.ok(!traffic.some(([,url])=>/tonight|target-suggestions/.test(url)));
  assert.deepEqual(errors,[]);
  console.log('PASS: read-only copy identification; exact Unicode/Windows paths; Simple/Pro 390/1280px; explicit access only; failures and stale replies; close/Escape; return to saved observations; GET-only.');
 } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1});
