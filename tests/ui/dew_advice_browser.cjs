const {timeHeaders,timeData}=require('./timezone_fixture.cjs');
// Chrome smoke: presentation only, real DOM/listeners, deterministic API fixtures.
// Run with Node and NODE_PATH pointing to Playwright; optional TONIGHT_ARTIFACT_DIR.
const {chromium}=require('playwright');
const fs=require('fs');
const path=require('path');
const assert=require('node:assert/strict');
const decision={status:'available',decision_id:'d',catalog_key:'M31',target:'Galaxie d’Andromède',
 target_decision_status:'recommended',action:'observe',night_date:'2026-10-04',
 window_start:'2026-10-04T20:00:00+02:00',window_end:'2026-10-04T22:00:00+02:00',recommended_hours:1.5,
 selected_filter:{name:'L-Pro',filter_type:'broadband'},astro_quality:{score:78,decision_score:78,decision_eligible:true,label:'good',limiting_factor:'clouds'},
 recommendation_confidence:.84,explanation:{positives:[{title:'Cible bien placée',value:'Altitude favorable pendant votre session'}],
 warnings:[{title:'Nuages à surveiller'}]},weather_trust:{validation_status:'validated',freshness_status:'fresh',
 timezone:'Europe/Zurich',snapshot_age_minutes:15,maximum_age_minutes:120},
 weather_decision:{admissibility:'caution',presentation:{label:'Vigilance météo',summary:'Passages nuageux possibles'}},
 alternatives:[{catalog_key:'M33',target:'Galaxie du Triangle',target_decision_status:'viable',reasons:[{message:'Autre cible exploitable'}]}]};
(async()=>{
 const web=path.resolve(__dirname,'../../astropilot/web');
 const browser=await chromium.launch({headless:true,channel:'chrome'});
 // Deliberately different from the site: decision hours must use the site timezone.
 const page=await browser.newPage({timezoneId:'America/New_York'});
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.route('https://nightmerit.test/**',route=>{
  const pathname=new URL(route.request().url()).pathname;
  if (pathname === '/ui/timezone-data.js') return route.fulfill({headers:timeHeaders,contentType:'text/javascript',body:timeData});
  const file=pathname==='/'?'index.html':{'/ui/timezone-authority.js':'timezone-authority.js','/ui/app.js':'app.js','/ui/styles.css':'styles.css','/ui/help.js':'help.js'}[pathname];
  return file?route.fulfill({headers:timeHeaders,body:fs.readFileSync(path.join(web,file)),contentType:file.endsWith('.js')?'text/javascript':file.endsWith('.css')?'text/css':'text/html'})
   :route.fulfill({headers:timeHeaders,status:503,contentType:'application/json',body:'{}'});
 });
 await page.goto('https://nightmerit.test/');
 await page.waitForFunction(()=>appliedUiMode!==null);
 for(const mode of ['simple','pro'])for(const width of [390,768,1280,1600]){
  await page.setViewportSize({width,height:900});
  await page.evaluate(mode=>{state.configuration={configured:true,site:{latitude:46.9,longitude:6.9,timezone:'Europe/Zurich'}};applyUiMode(mode);},mode);
  // Advice follows the supplied dew assessment; it neither assumes ownership
  // nor changes the decision, risk level, eligibility or selected equipment.
  for(const level of ['high','medium','low',null]){
   await page.evaluate(({decision,level})=>{
    const d=structuredClone(decision);
    if(level)d.dew_risk={level};else delete d.dew_risk;
    window.dewInput=d;window.dewBefore=JSON.stringify(d);renderDecision(d);
   },{decision,level});
   const warning=await page.locator('#decision-warning').innerText();
   if(level==='high'){
    assert.match(warning,/Rosée : risque élevé/);
    assert.match(warning,/Si vous disposez d’un chauffage antibuée/);
    assert.match(warning,/vérifiez l’absence de condensation sur l’optique avant les poses/);
    assert.equal(await page.locator('#decision-warning').isVisible(),true);
   }else assert.doesNotMatch(warning,/chauffage antibuée/);
   assert.equal(await page.evaluate(()=>JSON.stringify(dewInput)===dewBefore),true);
  }
  await page.evaluate(decision=>renderDecision(decision),decision);
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
 }
 assert.deepEqual(errors,[]);
 await browser.close();
 console.log('PASS: dew advice only on high risk, Simple/Pro × 4 widths; decision unchanged; no personal data used.');
})().catch(e=>{console.error(e);process.exit(1)});
