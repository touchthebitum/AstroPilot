const {timeHeaders,timeData}=require('./timezone_fixture.cjs');
const {chromium}=require('playwright');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
(async()=>{
 const web=path.resolve(__dirname,'../../astropilot/web');
 const browser=await chromium.launch({headless:true,chromiumSandbox:true,
  ...(process.env.NIGHTMERIT_TEST_CHROME?{executablePath:process.env.NIGHTMERIT_TEST_CHROME}:{channel:'chrome'})});
 try {
  const context=await browser.newContext({viewport:{width:390,height:844}});
  let requestCount=0,release;
  await context.route('http://nightmerit.test/**',async route=>{
   const url=new URL(route.request().url());
   if(url.pathname==='/ui/timezone-data.js')return route.fulfill({headers:timeHeaders,contentType:'text/javascript',body:timeData});
   if(url.pathname==='/')return route.fulfill({headers:timeHeaders,contentType:'text/html',body:fs.readFileSync(path.join(web,'index.html'),'utf8').replaceAll('__ASTROPILOT_SESSION_TIMING__','').replaceAll('__ASTROPILOT_ASSET_TOKEN__','review')});
   const file={'/ui/timezone-authority.js':'timezone-authority.js','/ui/app.js':'app.js','/ui/styles.css':'styles.css'}[url.pathname];
   if(file)return route.fulfill({headers:timeHeaders,contentType:file.endsWith('.js')?'text/javascript':'text/css',body:fs.readFileSync(path.join(web,file),'utf8')});
   if(url.pathname==='/v1/tonight') {
    requestCount++;await new Promise(resolve=>release=resolve);
    return route.fulfill({headers:timeHeaders,contentType:'application/json',body:JSON.stringify({status:'available',decision_id:'abandoned'})}).catch(()=>{});
   }
   return route.fulfill({headers:timeHeaders,status:503,contentType:'application/json',body:'{}'});
  });
  const page=await context.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto('http://nightmerit.test/');await page.waitForFunction(()=>state.view==='configuration_error');
  await page.evaluate(()=>{
   const schedule=window.setTimeout.bind(window),cancel=window.clearTimeout.bind(window);let seq=-1;window.analysisTimers=new Map();
   window.setTimeout=(fn,ms,...args)=>{if(ms===10000||ms===90000){const id=seq--;analysisTimers.set(id,{fn,ms});return id;}return schedule(fn,ms,...args);};
   window.clearTimeout=id=>{if(id<0)analysisTimers.delete(id);else cancel(id);};
   window.fireAnalysisTimer=ms=>{const [id,timer]=[...analysisTimers].find(([,t])=>t.ms===ms);analysisTimers.delete(id);timer.fn();};
   state.configuration={configured:true,profile_revision:1,site:{name:'Synthetic',latitude:46.8,longitude:6.5,timezone:'Europe/Zurich'},equipment:{preset_id:'samyang_183'},projects:{}};
   state.configurationDraft=draftFromConfiguration(state.configuration);setView('availability');
   window.pendingAnalysis=loadTonight({mode:'all_night'});
  });
  await page.waitForFunction(()=>analysisTimers.size===2);
  await page.evaluate(()=>fireAnalysisTimer(10000));
  assert.equal(await page.locator('#analysis-wait').isVisible(),true);
  assert.match(await page.locator('#analysis-wait').innerText(),/plus de temps/);
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
  if(process.env.NIGHTMERIT_TEST_SCREENSHOT)await page.screenshot({path:process.env.NIGHTMERIT_TEST_SCREENSHOT});
  await page.evaluate(async()=>{fireAnalysisTimer(90000);await pendingAnalysis;});
  assert.equal(await page.evaluate(()=>state.view),'availability');
  assert.equal(await page.locator('#availability-error').isVisible(),true);
  assert.match(await page.locator('#availability-error').innerText(),/90 secondes/);
  assert.equal(await page.evaluate(()=>state.requestingRecommendation),false);
  assert.equal(await page.locator('#request-recommendation').isDisabled(),false);
  assert.deepEqual(await page.evaluate(()=>state.availability),{mode:'all_night'});
  assert.equal(await page.evaluate(()=>analysisTimers.size),0);
  assert.equal(requestCount,1);release();
  assert.deepEqual(errors,[]);
  console.log('PASS: slow notice, 390px layout, bounded wait, restored controls and preserved availability; browser sandbox enabled.');
 } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
