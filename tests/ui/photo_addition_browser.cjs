// Real local API + isolated fictitious server fixture. No intercepted requests or UI state injection.
const {chromium}=require('playwright');
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
(async()=>{
 const origin=process.env.NIGHTMERIT_PHOTOS_TEST_URL||'http://127.0.0.1:18493';
 const out=process.env.NIGHTMERIT_PROOF_DIR;
 const browser=await chromium.launch({headless:true,executablePath:process.env.NIGHTMERIT_TEST_CHROME});
 try{
  const page=await browser.newPage(),errors=[],posts=[];
  page.on('pageerror',e=>errors.push(e.message));
  page.on('request',r=>{if(r.method()==='POST')posts.push({url:new URL(r.url()).pathname,body:r.postDataJSON()});});
  await page.goto(origin);await page.locator('#nav-projects').waitFor();await page.locator('#nav-projects').click();
  await page.getByRole('button',{name:'Ajouter mes photos conservées',exact:true}).click();
  await page.locator('#photos-inputs').waitFor({state:'visible'});
  assert.match(await page.locator('#photos-choice').innerText(),/OIII/);
  await page.locator('#photos-frames').fill('8');await page.locator('#photos-seconds').fill('300');
  assert.match(await page.locator('#photos-preview').innerText(),/0 h 40.*13 h 35.*14 h 15.*20 h/);
  assert.equal(posts.length,0,'preview must not write');
  let cases=0;
  for(const mode of ['simple','pro'])for(const width of [390,768,1024,1440]){
   // Presentation preference via the real control, no application state injection.
   await page.locator('#photos-close').click();await page.locator('#ui-mode').selectOption(mode);
   await page.getByRole('button',{name:'Ajouter mes photos conservées',exact:true}).click();
   await page.locator('#photos-inputs').waitFor({state:'visible'});
   await page.locator('#photos-frames').fill('8');await page.locator('#photos-seconds').fill('300');
   await page.setViewportSize({width,height:900});
   assert.equal(await page.locator('#photos-dialog').evaluate(e=>e.scrollWidth<=e.clientWidth),true);
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
   assert.match(await page.locator('#photos-preview').innerText(),/14 h 15/);
   if(out)await page.screenshot({path:path.join(out,`photos-${mode}-${width}.png`)});
   cases++;
  }
  const before=(await (await page.request.get(origin+'/v1/executions/photos-fictives/session')).json());
  assert.equal(before.current_acquired_seconds,48900);assert.equal(before.credit,null);
  await page.locator('#photos-submit').click();
  await page.locator('#photos-status.confirmation-success').waitFor();
  assert.match(await page.locator('#photos-status').innerText(),/14 h 15.*5 h 45/);
  assert.equal(await page.locator('#photos-submit').isVisible(),false);
  assert.equal(posts.filter(x=>x.url==='/v1/outcome-evidence').length,1);
  assert.equal(posts.filter(x=>x.url.endsWith('/intent-progress-credit')).length,1);
  assert.equal(posts.length,2,'one click, existing completed session, two durable stages only');
  if(out)await page.screenshot({path:path.join(out,'photos-confirmation.png')});
  await page.locator('#photos-close').click();await page.reload();
  await page.locator('#nav-projects').click();await page.getByRole('button',{name:'Ajouter mes photos conservées',exact:true}).click();
  await page.getByText(/Déjà ajouté :/).waitFor();
  assert.equal(await page.locator('#photos-submit').isVisible(),false);
  assert.equal(posts.length,2,'reopening never adds credit');
  assert.deepEqual(errors,[]);
  const after=await (await page.request.get(origin+'/v1/executions/photos-fictives/session')).json();
  assert.equal(after.current_acquired_seconds,51300);assert.equal(after.remaining_hours,5.75);assert.equal(after.evidence.length,1);
  if(out)fs.writeFileSync(path.join(out,'navigateur-api-reelle.json'),JSON.stringify({result:'PASS',cases,http_mocked:false,ui_state_injection:false,binary_tested:false,profile:'strictly fictitious',posts,after},null,2));
  console.log('PASS: 8 responsive Simple/Pro views; real API, one confirmation, exact OIII total, no replay credit, refresh.');
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exit(1)});
