const {timeHeaders,timeData}=require('./timezone_fixture.cjs');
const {chromium}=require('playwright');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
(async()=>{
 const web=path.resolve(__dirname,'../../astropilot/web');
 const browser=await chromium.launch({headless:true,chromiumSandbox:true,
  ...(process.env.NIGHTMERIT_TEST_CHROME?{executablePath:process.env.NIGHTMERIT_TEST_CHROME}:{channel:'chrome'})});
 try{
  const context=await browser.newContext({timezoneId:'America/New_York'}),writes=[];let sessions=[],fail=false;
  await context.route('http://127.0.0.1:18461/**',async route=>{
   const url=new URL(route.request().url()),method=route.request().method();
   if(method!=='GET')writes.push({path:url.pathname,body:route.request().postDataJSON()});
   if(url.pathname==='/ui/timezone-data.js')return route.fulfill({headers:timeHeaders,contentType:'text/javascript',body:timeData});
   if(url.pathname==='/')return route.fulfill({headers:timeHeaders,contentType:'text/html',body:fs.readFileSync(path.join(web,'index.html'),'utf8').replaceAll('__ASTROPILOT_SESSION_TIMING__','').replaceAll('__ASTROPILOT_ASSET_TOKEN__','review')});
   const file={'/ui/timezone-authority.js':'timezone-authority.js','/ui/app.js':'app.js','/ui/styles.css':'styles.css'}[url.pathname];
   if(file)return route.fulfill({headers:timeHeaders,contentType:file.endsWith('.js')?'text/javascript':'text/css',body:fs.readFileSync(path.join(web,file),'utf8')});
   if(url.pathname==='/v1/missions/mission/executions')return route.fulfill({headers:timeHeaders,json:sessions});
   if(url.pathname==='/v1/tonight')return route.fulfill({headers:timeHeaders,status:fail?503:200,json:fail?{detail:{code:'weather_unavailable'}}:{status:'no_candidate',creation_refusal:'no_eligible_acquisition_intent'}});
   return route.fulfill({headers:timeHeaders,status:503,json:{}});
  });
  const page=await context.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto('http://127.0.0.1:18461/');await page.waitForFunction(()=>state.view==='configuration_error');


  const reports=[];
  for(const width of [390,768,1280,1600]){
   await page.setViewportSize({width,height:900});
   await page.evaluate(()=>{
    state.fieldObservationDraftContext={timezone:'Europe/Zurich'};
    state.visibleObservationsForContext=[{observation_id:'fictive',observed_at_utc:'2026-10-30T20:10:00Z',conditions:{temperature_c:8.3,relative_humidity_percent:65,cloud_state:'partly_cloudy',seeing:'fair',moon_halo:false,surface_condition:'dew_present',wind_speed_kmh:null}}];
    const n=(variable,forecast,observed,unit)=>({variable,status:'comparable',forecast,observed,unit,signed_error:forecast-observed,absolute_error:Math.abs(forecast-observed),reasons:[]});
    globalThis.fictiveComparison={observation_id:'fictive',status:'comparable',reasons:[],results:[n('temperature_c',4.6,8.3,'°C'),n('relative_humidity_percent',84,65,'%'),{variable:'cloud_cover_percent',status:'comparable',forecast:'clear',observed:'partly_cloudy',outcome:'mismatch',unit:'%',reasons:[]}]};
    globalThis.fictiveOriginal=JSON.stringify(fictiveComparison);
    document.querySelector('#field-observation-dialog').showModal();
    document.querySelector('#observation-title').textContent='Comparaison fictive';
    renderOutcomeEvaluation(fictiveComparison,['Votre relevé est conservé.']);
   });
   for(const mode of ['simple','pro','simple']){
    await page.locator('#ui-mode').selectOption(mode,{force:true});
    const result=await page.locator('#outcome-result').textContent();
    if(mode==='simple'){
     assert.match(result,/3,7 °C plus élevée/);assert.match(result,/19 points de pourcentage plus faible/);
     assert.match(result,/ciel clair prévu, partiellement nuageux observé/);
     assert.match(result,/non comparées ici : Seeing, État de la surface, Halo lunaire/);
     assert.doesNotMatch(result,/erreur signée|erreur absolue/);
    }else{assert.match(result,/erreur signée/);assert.match(result,/-3,7 °C/);}
    assert.match(result,/Votre relevé est conservé/);
    assert.equal(await page.evaluate(()=>JSON.stringify(fictiveComparison)===fictiveOriginal),true);
    await page.locator('#outcome-result').scrollIntoViewIfNeeded();
    assert.equal(await page.locator('#field-observation-dialog').evaluate(el=>el.scrollWidth<=el.clientWidth),true);
    reports.push({mode,width,text:result});
    if(process.argv[2]&&width===1280)await page.screenshot({path:path.join(process.argv[2],mode+'.png')});
   }
   await page.evaluate(()=>document.querySelector('#field-observation-dialog').close());
  }
  assert.deepEqual(writes,[]);assert.deepEqual(errors,[]);
  if(process.argv[2])fs.writeFileSync(path.join(process.argv[2],'resultats.json'),JSON.stringify(reports,null,2));
  console.log('PASS: Simple/Pro/Simple × 4 tailles, écarts lisibles, avertissements conservés, données inchangées, aucun POST et aucun débordement.');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
