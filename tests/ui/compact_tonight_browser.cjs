// Chrome smoke: presentation only, real DOM/listeners, deterministic API fixtures.
// Run with Node and NODE_PATH pointing to Playwright; optional TONIGHT_ARTIFACT_DIR.
const {chromium}=require('playwright');
const fs=require('fs');
const path=require('path');
const assert=require('node:assert/strict');
const decision={status:'available',decision_id:'d',catalog_key:'M31',target:'Galaxie d’Andromède',
 target_decision_status:'recommended',action:'observe',night_date:'2026-10-04',
 window_start:'2026-10-04T20:00:00+02:00',window_end:'2026-10-04T22:00:00+02:00',recommended_hours:1.5,
 selected_filter:{name:'L-Pro',filter_type:'broadband'},astro_quality:{score:78,label:'good',limiting_factor:'clouds'},
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
 await page.route('http://nightmerit.test/**',route=>{
  const pathname=new URL(route.request().url()).pathname;
  const file=pathname==='/'?'index.html':{'/ui/app.js':'app.js','/ui/styles.css':'styles.css','/ui/help.js':'help.js'}[pathname];
  return file?route.fulfill({body:fs.readFileSync(path.join(web,file)),contentType:file.endsWith('.js')?'text/javascript':file.endsWith('.css')?'text/css':'text/html'})
   :route.fulfill({status:503,contentType:'application/json',body:'{}'});
 });
 await page.goto('http://nightmerit.test/');
 await page.waitForFunction(()=>appliedUiMode!==null);
 const positions=[];
 for(const mode of ['simple','pro'])for(const width of [390,1280]){
  await page.setViewportSize({width,height:800});
  await page.evaluate(({mode,decision})=>{
   state.configuration={configured:true,site:{latitude:46.9,longitude:6.9,timezone:'Europe/Zurich'}};
   applyUiMode(mode);renderDecision(decision);
   window.scrollTo(0,0);
  },{mode,decision});
  const essential=page.locator('#decision-essential');
  for(const id of ['recommendation','target-name','window-value','duration-value','filter-value','decision-reason','open-mission'])
   assert.equal(await essential.locator('#'+id).isVisible(),true,id);
  assert.match(await essential.innerText(),/Observer cette cible/i);
  assert.match(await essential.innerText(),/Galaxie d’Andromède/);
  assert.equal(await page.locator('#window-value').innerText(),'20:00 — 22:00');
  assert.equal(await page.locator('#duration-value').innerText(),'1 h 30');
  assert.match(await page.locator('#filter-value').innerText(),/L-Pro/);
  assert.match(await page.locator('#decision-reason').innerText(),/Facteur principal/);
  assert.equal(await page.locator('#open-mission').isEnabled(),true);
  assert.equal(await page.locator('#quality-score').isVisible(),mode==='pro');
  assert.equal(await page.locator('#recommendation-confidence-value').isVisible(),mode==='pro');
  assert.equal(await page.locator('#insights-list').isVisible(),mode==='pro');
  assert.equal(await page.locator('#decision-warning').isVisible(),true);
  assert.match(await page.locator('#decision-warning').innerText(),/Passages nuageux possibles.*Nuages à surveiller/);
  assert.equal(await page.locator('#classic-weather-age').isVisible(),true);
  const reason=await page.locator('#decision-reason').innerText();
  assert.equal((await page.locator('#insights-list').textContent()).includes(reason),false);
  if(mode==='simple'){
   await page.locator('#decision-metrics > summary').click();
   assert.equal(await page.locator('#quality-score').isVisible(),true);
   assert.equal(await page.locator('#quality-score').innerText(),'78');
   await page.locator('#decision-metrics > summary').click();
  }
  const styles=await page.evaluate(()=>{
   const a=getComputedStyle(ui.openMission),b=getComputedStyle(document.querySelector('.alternative-button'));
   return {primary:a.backgroundColor,secondary:b.backgroundColor,weightA:Number(a.fontWeight),weightB:Number(b.fontWeight)};
  });
  assert.notEqual(styles.primary,styles.secondary);assert.ok(styles.weightA>styles.weightB);
  const measured=await page.evaluate(()=>Object.fromEntries(['recommendation','target-name','open-mission','window-value','filter-value'].map(id=>{
   const rect=document.getElementById(id).getBoundingClientRect();return [id,Math.round(rect.top+scrollY)];
  })));
  positions.push({mode,width,positions:measured});
  // Read-only audit of e5d4df6, same fixture and configured site, at scrollY=0.
  const baseline=width===390?{'open-mission':883,'window-value':1034,'filter-value':1259}
   :{'open-mission':698,'window-value':816,'filter-value':818};
  for(const [id,y] of Object.entries(baseline))assert.ok(measured[id]<y,`${id} must improve over baseline`);
  assert.ok(measured['window-value']<700);assert.ok(measured['filter-value']<750);
  assert.ok(measured['open-mission']<850,'CTA must stay close to first viewport, including weather warning');
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
  assert.equal(await page.locator('#decision').evaluate(e=>e.scrollWidth<=e.clientWidth),true);
  assert.equal(await page.evaluate(()=>Boolean(ui.openMission.compareDocumentPosition(document.querySelector('.alternative-button'))&Node.DOCUMENT_POSITION_FOLLOWING)),true);
  await page.locator('#open-mission').focus();
  await page.keyboard.press('Tab');
  assert.equal(await page.evaluate(()=>document.activeElement.parentElement.id),'decision-metrics');
  // Real bound listeners retain the exact selection arguments; no mission is persisted.
  await page.evaluate(()=>{window.originalAccept=acceptRecommendation;window.accepted=[];acceptRecommendation=options=>accepted.push({source:options.source,key:options.selectedCatalogKey,id:options.expectedDecisionId});});
  await page.locator('#open-mission').click();await page.locator('.alternative-button').click();
  assert.deepEqual(await page.evaluate(()=>accepted),[{source:'primary_recommendation',key:'M31',id:'d'},{source:'alternative',key:'M33',id:'d'}]);
  await page.evaluate(()=>{acceptRecommendation=originalAccept;window.scrollTo(0,0)});
  if(process.env.TONIGHT_ARTIFACT_DIR){fs.mkdirSync(process.env.TONIGHT_ARTIFACT_DIR,{recursive:true});await page.screenshot({path:path.join(process.env.TONIGHT_ARTIFACT_DIR,`tonight-${mode}-${width}.png`),fullPage:true});}
  // Warnings stay outside closed disclosures even with stale/unknown metadata.
  for(const variant of ['stale','unknown','insufficient','no-intent','missing']){
   await page.evaluate(({decision,variant})=>{
    const d=structuredClone(decision);
    if(variant==='stale') d.weather_trust.freshness_status='stale';
    if(variant==='unknown') delete d.weather_trust;
    if(variant==='insufficient')d.target_decision_status='insufficient_evidence';
    if(variant==='no-intent')d.acquisition_intent_selection_status='no_eligible_intent';
    if(variant==='missing'){delete d.selected_filter;delete d.window_start;delete d.window_end;delete d.recommended_hours;}
    renderDecision(d);
   },{decision,variant});
   assert.equal(await page.locator('#decision-warning').isVisible(),true);
   if(variant==='stale')assert.match(await page.locator('#decision-warning').innerText(),/Données météo périmées/);
   if(variant==='unknown')assert.match(await page.locator('#decision-warning').innerText(),/Confiance météo non confirmée/);
   if(['insufficient','no-intent'].includes(variant))assert.equal(await page.locator('#open-mission').isVisible(),false);
   if(variant==='missing'){
    assert.equal(await page.locator('#window-value').innerText(),'À confirmer');
    assert.equal(await page.locator('#filter-value').innerText(),'Filtre non précisé');
   }
  }
  // Known type and actual hardware are distinct. No hardware is invented.
  await page.evaluate(decision=>renderDecision({...decision,selected_acquisition_intent_id:'nb',acquisition_intent_selection_status:'unique',
   viable_acquisition_intent_ids:['nb'],acquisition_intent_options:[{acquisition_intent_id:'nb',label:'Bande étroite · Hα'}],
   acquisition_intent_assessments:[{acquisition_intent_id:'nb',label:'Bande étroite · Hα'}],selected_filter:{name:'L-eXtreme'}}),decision);
  assert.match(await page.locator('#filter-value').innerText(),/Type requis : Bande étroite/);
  assert.equal(await page.locator('#filter-note').innerText(),'Filtre matériel : L-eXtreme');
  await page.evaluate(decision=>renderDecision({...decision,target:'Cible'.repeat(35),selected_filter:{name:'Filtre'.repeat(40)},
   alternatives:[{...decision.alternatives[0],target:'Alternative'.repeat(40)}]}),decision);
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true,'long names must wrap');
  assert.equal(await page.locator('#decision').evaluate(e=>e.scrollWidth<=e.clientWidth),true);
  for(const stage of ['no_productive_slice','continuous_window_too_short','unknown']){
   await page.evaluate(stage=>{state.availability={mode:'full_night'};showTonightUnavailable({status:'no_productive_window',actionability_refusal:{
    conclusion:'no_productive_window',status:'constraints_refusal',refusal_stage:stage,best_productive_window_minutes:30,
    required_continuous_minutes:60,productivity_breakdown:{best_slice_score:.39,productive_slice_threshold:.5,
    best_slice_tie_count:1,evaluated_slice_count:8,losses:{cloud:.4}}}})},stage);
   assert.match(await page.locator('#message-body').innerText(),/Réessayez plus tard/);
   assert.doesNotMatch(await page.locator('#message-body').innerText(),/seuil|points|tranches/i);
   assert.equal(await page.locator('#message-details').evaluate(e=>e.open),mode==='pro');
   assert.match(await page.locator('#message-technical').textContent(),/seuil|preuves/i);
   assert.equal(await page.locator('#message-retry').innerText(),'Réessayer plus tard');
   assert.equal(await page.locator('#message-edit-availability').isVisible(),true);
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
  }
  await page.locator('#message-edit-availability').click();
  assert.equal(await page.evaluate(()=>state.view),'availability');
  await page.evaluate(()=>{state.availability=null;showTonightUnavailable({status:'no_recommendation'})});
  assert.equal(await page.locator('#message-edit-availability').isVisible(),false);
  assert.match(await page.locator('#message-body').innerText(),/Réessayez plus tard/);
  await page.evaluate(()=>showTonightUnavailable({status:'weather_refused',weather_decision:{presentation:{label:'Conditions insuffisantes',summary:'Données météo périmées : aucune mission autorisée.'}}}));
  assert.match(await page.locator('#message-body').innerText(),/Données météo périmées.*Réessayez plus tard/);
  await page.evaluate(()=>showMessage('Erreur réseau','Connexion impossible'));
  assert.equal(await page.locator('#message-details').isVisible(),false);
  assert.equal(await page.locator('#message-retry').innerText(),'Réessayer');
 }
 assert.deepEqual(errors,[]);
 console.log(JSON.stringify({positions,errors},null,2));
 await browser.close();
})().catch(e=>{console.error(e);process.exit(1)});
