// Real local server, strict fictitious profile; no weather calls or UI state injection.
const {chromium}=require('playwright'), assert=require('node:assert/strict'), fs=require('node:fs'), path=require('node:path');
(async()=>{
 const origin=process.env.NIGHTMERIT_CONDUCTOR_URL||'http://127.0.0.1:18811';
 const out=process.env.NIGHTMERIT_PROOF_DIR;
 const browser=await chromium.launch({headless:true,executablePath:process.env.NIGHTMERIT_TEST_CHROME});
 try {
  const page=await browser.newPage({viewport:{width:1280,height:1000}}),errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.goto(origin);await page.locator('#nav-projects').waitFor({state:'visible'});
  const id='conductor-photos-fictives';
  if(process.env.NIGHTMERIT_RESTART !== '1'){
   for(const [url,body] of [
    ['/v1/executions',{execution_id:id,mission_id:'mission-1'}],
    ['/v1/execution-transitions',{execution_id:id,mission_id:'mission-1',status:'in_progress',actual_start:'2026-09-12T20:10:00Z',actual_end:null,actual_duration:null}]
   ]) {const r=await page.request.post(origin+url,{data:body});assert.equal(r.status(),200,await r.text());}
   await page.locator('#beginner-saved-missions summary').click();
   await page.locator('#open-saved-mission').click();
   await page.locator(`#session-choice option[value="${id}"]`).waitFor({state:'attached'});
   await page.locator('#session-choice').selectOption(id);
   await page.locator('#session-complete').waitFor({state:'visible'});
   await page.locator('#session-complete').click();
   await page.locator('#beginner-tri').waitFor({state:'visible'});
   assert.equal(await page.locator('#session-evidence').isVisible(),false);
   assert.equal(await page.locator('#session-credit').isVisible(),false);
   await page.getByRole('button',{name:'Mes images sont triées : les ajouter',exact:true}).click();
   await page.waitForFunction(id=>document.querySelector('#photos-choice').value===id,id);
   await page.locator('#photos-frames').fill('8');await page.locator('#photos-seconds').fill('300');
   assert.match(await page.locator('#photos-preview').innerText(),/0 h 40.*0 h 08 45 s.*0 h 48 45 s/);
   await page.locator('#ui-mode').evaluate(e=>{e.value='pro';e.dispatchEvent(new Event('change',{bubbles:true}))});
   assert.equal(await page.locator('#photos-frames').inputValue(),'8');
   await page.locator('#ui-mode').evaluate(e=>{e.value='simple';e.dispatchEvent(new Event('change',{bubbles:true}))});
   if(out)await page.screenshot({path:path.join(out,'ajouter-avant.png')});
   await page.locator('#photos-submit').click();await page.locator('#photos-status.confirmation-success').waitFor();
   assert.match(await page.locator('#photos-status').innerText(),/0 h 48 45 s.*14 h 11 15 s/);
   assert.equal(await page.locator('#photos-submit').isVisible(),false);
   await page.locator('#photos-close').click();
  }
  await page.locator('#nav-projects').click();
  await page.getByRole('button',{name:'Ajouter mes photos conservées',exact:true}).click();
  await page.locator('#photos-choice').selectOption(id);
  await page.getByText(/Déjà ajouté :/).waitFor();
  assert.equal(await page.locator('#photos-submit').isVisible(),false);
  const session=await(await page.request.get(origin+`/v1/executions/${id}/session`)).json();
  assert.equal(session.current_acquired_seconds,2925);assert.equal(session.session_credit_seconds,2400);
  assert.equal(session.evidence.length,1);assert.deepEqual(errors,[]);
  if(out){await page.screenshot({path:path.join(out,process.env.NIGHTMERIT_RESTART==='1'?'ajouter-redemarrage.png':'ajouter-apres.png')});fs.writeFileSync(path.join(out,process.env.NIGHTMERIT_RESTART==='1'?'session-redemarrage.json':'session-ajout.json'),JSON.stringify({session,errors,api_mocked:false,ui_state_injected:false},null,2));}
  console.log('PASS: actual session completion, direct addition of 40 min, no duplicate, existing 8 min 45 s preserved.');
 } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exit(1)});
