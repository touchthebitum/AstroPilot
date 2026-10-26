// Production UI and handlers, synthetic evidence only. Never opens a user profile.
const {timeHeaders,timeData}=require('./timezone_fixture.cjs');
const {chromium}=require('playwright');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const decision={status:'available',decision_id:'nightline-test',catalog_key:'M42',target:'M42',
 target_decision_status:'recommended',action:'observe',night_date:'2026-10-26',
 window_start:'2026-10-26T20:00:00+01:00',window_end:'2026-10-26T22:00:00+01:00',recommended_hours:2,
 selected_filter:{name:'Baader Hα 6,5 nm',filter_type:'Ha'},
 explanation:{positives:[{title:'Cible bien placée',value:'Justification du scénario de test'}],warnings:[{title:'Humidité à surveiller'}]},
 weather_trust:{validation_status:'validated',freshness_status:'fresh',timezone:'Europe/Zurich',snapshot_age_minutes:5,maximum_age_minutes:90},
 weather_decision:{admissibility:'caution',presentation:{label:'Vigilance météo',summary:'Surveillez la buée sur l’optique.'}}};
const mission={mission_id:'nightline-mission',decision_id:decision.decision_id,target:'M42',site_name:'Buttes',
 window_start:decision.window_start,window_end:decision.window_end,recommended_hours:2,expected_gain:.2,
 selected_filter:decision.selected_filter,equipment:['Samyang 135 mm','ZWO ASI183MM'],
 tasks:[{title:'Installer le matériel',start:'2026-10-26T19:30:00+01:00',end:'2026-10-26T19:40:00+01:00'},
 {title:'Effectuer la mise en station',start:'2026-10-26T19:40:00+01:00',end:'2026-10-26T19:50:00+01:00'},
 {title:'Prendre les flats',start:'2026-10-26T22:00:00+01:00',end:'2026-10-26T22:10:00+01:00'}]};
(async()=>{
 const browser=await chromium.launch({headless:true,channel:'chrome'});
 try{
 const page=await browser.newPage({timezoneId:'America/New_York'}),errors=[],requests=[];
 page.on('pageerror',e=>errors.push(e.message));
 const web=path.resolve(__dirname,'../../astropilot/web');
 await page.route('https://nightline.test/**',route=>{
  const p=new URL(route.request().url()).pathname;requests.push([route.request().method(),p]);
  if(p==='/ui/timezone-data.js')return route.fulfill({headers:timeHeaders,contentType:'text/javascript',body:timeData});
  const name=p==='/'?'index.html':p.startsWith('/ui/')?path.basename(p):'';
  const file=path.join(web,name);
  if(name&&fs.existsSync(file)&&fs.statSync(file).isFile())return route.fulfill({headers:timeHeaders,body:fs.readFileSync(file,'utf8').replaceAll('__ASTROPILOT_SESSION_TIMING__',''),contentType:name.endsWith('.js')?'text/javascript':name.endsWith('.css')?'text/css':'text/html'});
  return route.fulfill({headers:timeHeaders,status:503,contentType:'application/json',body:'{}'});
 });
 await page.goto('https://nightline.test/');await page.waitForFunction(()=>appliedUiMode!==null);
 const cases=[];
 for(const mode of ['simple','pro'])for(const width of [320,390,768,1024,1280]){
  await page.setViewportSize({width,height:900});
  await page.evaluate(({mode,decision})=>{
   state.configuration={configured:true,site:{name:'Buttes',latitude:46.9,longitude:6.9,bortle:4,timezone:'Europe/Zurich'},preset_equipment:[],available_equipment:[]};
   state.configurationDraft={site:state.configuration.site,equipment:{preset_id:'samyang_183'},projects:{}};
   applyUiMode(mode);renderDecision(decision);window.scrollTo(0,0);
  },{mode,decision});
  assert.equal(await page.locator('#window-value').innerText(),'20:00 — 22:00');
  assert.match(await page.locator('#decision-warning').innerText(),/buée/);
  assert.equal(await page.locator('#open-mission').isVisible(),true);
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
  assert.equal(await page.locator('#decision').evaluate(e=>e.scrollWidth<=e.clientWidth),true);
  if(width<=390){
   const bounds=await page.locator('#open-mission').boundingBox();assert(bounds.height>=48);assert(bounds.y<850);
   assert.equal(await page.locator('#ui-mode').evaluate(e=>getComputedStyle(e).fontSize),'16px');
  }
  // The common options remain reachable in Pro too, without a permanently expanded toolbar.
  assert.equal(await page.locator('#header-options').evaluate(e=>e.open),false);
  await page.locator('#header-options > summary').click();assert.equal(await page.locator('#data-context-open').isVisible(),true);
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
  await page.locator('#header-options > summary').click();
  const artifact=process.env.NIGHTLINE_ARTIFACT_DIR;
  if(artifact&&mode==='simple'&&[390,768,1280].includes(width)){fs.mkdirSync(artifact,{recursive:true});await page.screenshot({path:path.join(artifact,`decision-${width}.png`),fullPage:true});}
  await page.evaluate(mission=>{state.acceptedMission={mission,windowTimezone:'Europe/Zurich'};renderMission(mission);ui.mission.showModal();},mission);
  assert.equal(await page.locator('#mission-window').innerText(),'20:00 — 22:00');
  assert.match(await page.locator('#mission-tasks').innerText(),/Trier les images/);
  assert.equal(await page.locator('#mission-dialog').evaluate(e=>e.scrollWidth<=e.clientWidth),true);
  await page.locator('#mission-dialog').evaluate(e=>e.scrollTop=e.scrollHeight);
  const close=await page.locator('#close-mission').boundingBox(),dialog=await page.locator('#mission-dialog').boundingBox();
  assert(close.y>=dialog.y&&close.y+close.height<=dialog.y+dialog.height,'mission close must remain visible after scrolling');
  await page.locator('#close-mission').click();assert.equal(await page.locator('#mission-dialog').evaluate(e=>e.open),false);
  await page.evaluate(()=>ui.mission.showModal());await page.keyboard.press('Escape');assert.equal(await page.locator('#mission-dialog').evaluate(e=>e.open),false);
  // Same native availability fields and values across widths and both modes.
  await page.evaluate(()=>{state.availability={mode:'fixed_window',start:'2026-10-26T20:00',end:'2026-10-26T22:00'};setView('availability');});
  await page.locator('input[name="availability-mode"][value="fixed_window"]').check();
  await page.locator('#availability-start').fill('2026-10-26T20:00');await page.locator('#availability-end').fill('2026-10-26T22:00');
  await page.selectOption('#ui-mode',mode==='simple'?'pro':'simple');
  assert.equal(await page.inputValue('#availability-start'),'2026-10-26T20:00');assert.equal(await page.inputValue('#availability-end'),'2026-10-26T22:00');
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
  await page.selectOption('#ui-mode',mode);
  if(artifact&&mode==='simple'&&[390,768,1280].includes(width))await page.screenshot({path:path.join(artifact,`availability-${width}.png`),fullPage:true});
  await page.evaluate(()=>{showTonightUnavailable({status:'no_productive_window'});});
  assert.equal(await page.locator('#message-state').isVisible(),true);assert.equal(await page.locator('#open-mission').isVisible(),false);
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
  cases.push({mode,width});
 }
 assert(requests.every(([method])=>method==='GET'),'visual checks must not write through the API');assert.deepEqual(errors,[]);
 console.log(JSON.stringify({result:'PASS',cases,read_only:true,mission_close_stays_visible:true,availability_preserved:true}));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1)});
