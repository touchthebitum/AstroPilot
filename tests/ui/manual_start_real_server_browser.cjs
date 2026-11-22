// All storage and execution requests reach the isolated real branch server.
const {chromium}=require('playwright');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const proof=process.env.NIGHTMERIT_PROOF_DIR,origin=process.env.NIGHTMERIT_SERVER_ORIGIN,scenario=process.env.NIGHTMERIT_START_SCENARIO;
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.NIGHTMERIT_TEST_CHROME,args:['--use-mock-keychain']});
 const errors=[],requests=[],writes=[];let cut=false,guardianRefusal=null;
 try{
  const page=await browser.newPage({timezoneId:'Europe/Zurich',serviceWorkers:'block'});
  page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/*',async route=>{
   const req=route.request(),u=new URL(req.url());assert.equal(u.origin,origin,'External or other-instance access forbidden');
   requests.push({method:req.method(),path:u.pathname});
   assert.notEqual(u.pathname,'/v1/tonight','No browser weather analysis allowed');
   if(req.method()!=='GET'){
    assert.equal(req.method(),'POST');assert(['/v1/executions','/v1/execution-transitions'].includes(u.pathname),'Only explicit execution commands allowed');
    writes.push({path:u.pathname,body:req.postDataJSON()});
    if(u.pathname==='/v1/execution-transitions'&&scenario==='guardian-refusal'){
     const response=await route.fetch({headers:{...req.headers(),'x-guardian-owner-instance-id':'stale-fictitious-instance'}});
     guardianRefusal={status:response.status(),body:await response.json()};
     return route.fulfill({response});
    }
    if(u.pathname==='/v1/execution-transitions'&&scenario==='lost-transition'&&!cut){
     const response=await route.fetch();assert.equal(response.status(),200,await response.text());cut=true;
     return route.abort('failed');
    }
   }
   return route.continue();
  });
  async function openPlan(){
   await page.waitForFunction(()=>state.configuration?.configured && !state.savedMissionLoading && state.savedMissions.length===1);
   await page.evaluate(()=>{setView('availability');const details=document.querySelector('#beginner-saved-missions');details.hidden=false;details.open=true;renderSavedMissionChoices();});
   await page.locator('#open-saved-mission').click();await page.waitForFunction(()=>state.missionConditionsReady);
  }
  await page.goto(origin);await openPlan();
  const baseline=await page.evaluate(async()=>{
   const p=await fetch('/v1/projects/Rosette/progress');if(!p.ok)throw Error(await p.text());return p.json();
  });
  assert.equal(await page.locator('#manual-start-dialog').isVisible(),false);
  await page.locator('#session-start').click();await page.locator('#manual-start-dialog').waitFor({state:'visible'});
  if(scenario==='unique'){
   await page.locator('#manual-start-cancel').click();assert.equal(writes.length,0);
   await page.locator('#session-start').click();await page.locator('#manual-start-dialog').waitFor({state:'visible'});
   await page.locator('#manual-start-confirm').evaluate(el=>{el.click();el.click();});
  }else await page.locator('#manual-start-confirm').click();
  await page.waitForFunction(()=>!state.sessionBusy);
  assert.deepEqual(writes.map(w=>w.path),['/v1/executions','/v1/execution-transitions']);
  let sessions=await page.evaluate(async()=>{const r=await fetch('/v1/execution-sessions');if(!r.ok)throw Error(await r.text());return r.json();});
  assert.equal(sessions.length,1);
  const executionId=sessions[0].execution.execution_id;
  if(scenario==='guardian-refusal'){
   assert.equal(guardianRefusal.status,409);assert.equal(guardianRefusal.body.code,'guardian_owner_instance_mismatch');
   assert.equal(sessions[0].execution.status,'not_started');assert.match(await page.locator('#session-status').innerText(),/transition non enregistrée/);
  }else{
   assert.equal(sessions[0].execution.status,'in_progress');
   if(scenario==='lost-transition')assert.match(await page.locator('#session-status').innerText(),/réponse incertaine/);
  }
  assert.equal(sessions[0].credit,null);assert.equal(sessions[0].session_credit_seconds,0);
  await page.screenshot({path:path.join(proof,'after-command.png'),fullPage:true});
  await page.reload();await openPlan();
  const after=await page.evaluate(async()=>({
   sessions:await (await fetch('/v1/execution-sessions')).json(),
   progress:await (await fetch('/v1/projects/Rosette/progress')).json(),
   guardian:await (await fetch(`/v1/executions/${currentSession().execution.execution_id}/guardian-renewal`)).json()
  }));
  assert.equal(after.sessions.length,1);assert.equal(after.sessions[0].execution.execution_id,executionId);
  assert.equal(after.sessions[0].execution.status,scenario==='guardian-refusal'?'not_started':'in_progress');
  assert.equal(after.sessions[0].credit,null);assert.deepEqual(after.progress,baseline);
  const totals=Object.fromEntries(after.progress.intent_progress_breakdown.map(p=>[p.acquisition_intent_id,p.effective_total_seconds]));
  assert.equal(totals.rosette_oiii,2400);assert.equal(totals.rosette_sii,1500);
  assert.match(await page.locator('#mission-weather-status').innerText(),/restent à revérifier/);
  if(scenario!=='guardian-refusal'){
   assert(after.guardian.guardian_mode_enabled);assert(after.guardian.owned_here);assert(after.guardian.renewal_eligible);
   await page.evaluate(()=>requestManualStart());assert.equal(writes.length,2);
  }else{
   assert.equal(after.guardian.owned_here,false);assert.equal(after.guardian.renewal_eligible,false);
  }
  assert.deepEqual(errors,[]);
  await page.screenshot({path:path.join(proof,'after-reload.png'),fullPage:true});
  fs.writeFileSync(path.join(proof,'browser-verification.json'),JSON.stringify({success:true,scenario,executionId,requests,writes,guardianRefusal,baseline,after,errors,server:'real branch server, real durable stores and Guardian adapter',weather:'synthetic only, no browser analysis'},null,2));
  console.log('PASS real server: '+scenario+'; unique durable session; counters 40/25 after reload.');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1});
