// Real DOM with fictitious API fixtures only; no live weather or existing profile.
const {chromium}=require('playwright');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {timeHeaders,timeData}=require('./timezone_fixture.cjs');
const decision={status:'available',decision_id:'fictitious-summary',catalog_key:'Rosette',target:'Rosette',
 target_decision_status:'recommended',action:'observe',night_date:'2026-11-21',
 window_start:'2026-11-21T20:00:00+01:00',window_end:'2026-11-21T22:00:00+01:00',recommended_hours:1.5,
 acquisition_intent_selection_status:'unique',selected_acquisition_intent_id:'rosette_oiii',viable_acquisition_intent_ids:['rosette_oiii'],
 acquisition_intent_options:[{acquisition_intent_id:'rosette_oiii',label:'OIII'}],
 selected_filter:{name:'Filtre OIII fictif',filter_type:'OIII'},
 astro_quality:{score:78,decision_score:78,decision_eligible:true,label:'good'},recommendation_confidence:.84,
 explanation:{positives:[{title:'Raison fournie',value:'Fenêtre du jeu fictif'}],warnings:[{title:'Vigilance du jeu fictif'}]},
 weather_trust:{provider:'simulated-fixture',validation_status:'validated',freshness_status:'fresh',timezone:'Europe/Zurich',snapshot_age_minutes:15,maximum_age_minutes:120},
 weather_decision:{admissibility:'caution',presentation:{label:'Vigilance météo',summary:'Avertissement conservé'}},
 project_comparison:[{project_id:'M42',filters:[{acquisition_intent_id:'m42_oiii',filter_type:'OIII',target_hours:9,acquired_hours:8,remaining_hours:1,status:'to_complete'}]},
 {project_id:'Rosette',filters:[{acquisition_intent_id:'rosette_oiii',filter_type:'OIII',target_hours:3,acquired_hours:40/60,remaining_hours:3-40/60,status:'to_complete'}]}]};
(async()=>{
 const browser=await chromium.launch({headless:true,channel:'chrome',args:['--use-mock-keychain']});
 try{
  const page=await browser.newPage({timezoneId:'America/New_York'}),errors=[],writes=[],cases=[];
  const web=path.resolve(__dirname,'../../astropilot/web');
  page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/*',route=>{
   const req=route.request(),url=new URL(req.url());
   if(req.method()!=='GET'){writes.push(url.pathname);return route.abort();}
   if(url.origin!=='https://nightmerit.test')return route.abort();
   if(url.pathname==='/ui/timezone-data.js')return route.fulfill({headers:timeHeaders,contentType:'text/javascript',body:timeData});
   const name=url.pathname==='/'?'index.html':url.pathname.startsWith('/ui/')?url.pathname.slice(4):null;
   if(name&&path.basename(name)===name&&fs.existsSync(path.join(web,name)))return route.fulfill({headers:timeHeaders,contentType:name.endsWith('.js')?'text/javascript':name.endsWith('.css')?'text/css':'text/html',body:fs.readFileSync(path.join(web,name))});
   return route.fulfill({headers:timeHeaders,status:503,json:{}});
  });
  await page.goto('https://nightmerit.test/');await page.waitForFunction(()=>appliedUiMode!==null);
  for(const mode of ['simple','pro'])for(const width of [390,1280]){
   await page.setViewportSize({width,height:900});
   const unchanged=await page.evaluate(({mode,d})=>{
    state.configuration={configured:true,site:{timezone:'Europe/Zurich',latitude:46.9,longitude:6.9}};applyUiMode(mode);
    const snapshot=()=>Object.fromEntries(['target-name','window-value','duration-value','filter-value','quality-score','decision-reason','decision-warning'].map(id=>[id,document.getElementById(id).textContent]));
    renderDecision({...d,project_comparison:undefined});const before=snapshot();
    const payload=JSON.stringify(d);renderDecision(d);
    return {before,after:snapshot(),payload_unchanged:JSON.stringify(d)===payload};
   },{mode,d:decision});
   assert.deepEqual(unchanged.before,unchanged.after);assert.equal(unchanged.payload_unchanged,true);
   const block=page.locator('#project-tonight-summary');assert.equal(await block.isVisible(),true);
   assert.equal(await block.locator('h3').innerText(),'Pour ce soir : Rosette — OIII');
   assert.match(await block.innerText(),/Objectif 3 h · Déjà acquis 40 min · Reste à faire 2 h 20/);
   assert.doesNotMatch(await block.innerText(),/M42|8 h|9 h/);
   assert.equal(await page.locator('#window-value').innerText(),'20:00 — 22:00');
   assert.match(await page.locator('#decision-reason').innerText(),/Raison fournie/);
   assert.match(await page.locator('#decision-warning').innerText(),/Vigilance du jeu fictif/);
   const bounds=await block.evaluate(e=>({left:e.getBoundingClientRect().left,right:e.getBoundingClientRect().right,overflow:e.scrollWidth>e.clientWidth}));
   assert.ok(bounds.left>=0&&bounds.right<=width&&!bounds.overflow,JSON.stringify(bounds));
   if(process.env.NIGHTMERIT_PROOF_DIR){fs.mkdirSync(process.env.NIGHTMERIT_PROOF_DIR,{recursive:true});await block.screenshot({path:path.join(process.env.NIGHTMERIT_PROOF_DIR,`resume-${mode}-${width}.png`)});}
   await page.evaluate(d=>{
    const pending={...d,status:'no_mission',creation_refusal:'preselection_evidence_cannot_authorize_mission',acquisition_intent_choice_available:true,
     acquisition_intent_selection_status:'no_clear_preference',selected_acquisition_intent_id:null,
     viable_acquisition_intent_ids:['rosette_oiii','rosette_sii'],acquisition_intent_options:[{acquisition_intent_id:'rosette_oiii',label:'OIII'},{acquisition_intent_id:'rosette_sii',label:'SII'}]};
    pending.project_comparison[1].filters.push({acquisition_intent_id:'rosette_sii',filter_type:'SII',target_hours:3,acquired_hours:25/60,remaining_hours:3-25/60,status:'to_complete'});
    window.pendingSummary=pending;renderDecision(pending);
   },decision);
   assert.match(await block.innerText(),/Filtre à confirmer/);assert.doesNotMatch(await block.innerText(),/Déjà acquis/);
   // The acceptance handler is covered separately; exercise its display with the canonical reply.
   await page.evaluate(()=>renderProjectTonightSummary(window.pendingSummary,'rosette_sii'));
   assert.match(await block.locator('h3').innerText(),/SII$/);assert.match(await block.innerText(),/Déjà acquis 25 min/);
   assert.doesNotMatch(await block.innerText(),/Filtre à confirmer|40 min/);
   await page.evaluate(()=>renderProjectTonightSummary(null,'other_intent'));
   assert.equal(await block.isVisible(),false);
   await page.evaluate(d=>renderDecision({...d,explanation:undefined}),decision);
   assert.equal(await page.locator('#decision-reason').innerText(),'Pourquoi : non précisé');
   await page.evaluate(d=>renderDecision({...d,status:'no_mission',target_decision_status:'not_recommended'}),decision);
   assert.equal(await block.isVisible(),false);
   await page.evaluate(d=>renderDecision({...d,project_comparison:undefined}),decision);
   assert.equal(await block.isVisible(),false);
   cases.push({mode,width,unchanged,bounds});
  }
  assert.deepEqual(errors,[]);assert.deepEqual(writes,[]);
  if(process.env.NIGHTMERIT_PROOF_DIR)fs.writeFileSync(path.join(process.env.NIGHTMERIT_PROOF_DIR,'verification.json'),JSON.stringify({success:true,cases,errors,writes,weather:'simulated fixtures; no live provider'},null,2));
  console.log('PASS: exact project/intent summary, mobile/Advanced, unchanged scores/selection/reasons/warnings/times, refusals, no writes');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1});
