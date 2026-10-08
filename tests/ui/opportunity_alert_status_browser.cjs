const {chromium} = require('playwright');
const fs = require('fs');
const path = require('path');
const assert = require('node:assert/strict');
(async () => {
 const browser = await chromium.launch({headless:true, channel:'chrome'});
 const page = await browser.newPage();
 const web = path.resolve(__dirname, '../../astropilot/web');
 let response = {state:'unknown'}, calls = [], fail = false, delay = 0;
 await page.route('http://nightmerit.test/**', async route => {
  const url = new URL(route.request().url());
  if(url.pathname === '/') return route.fulfill({contentType:'text/html',body:fs.readFileSync(path.join(web,'index.html'),'utf8')});
  if(url.pathname.startsWith('/ui/')) {
   const filename = path.basename(url.pathname);
   return route.fulfill({contentType:filename.endsWith('.js')?'text/javascript':'text/css',body:fs.readFileSync(path.join(web,filename),'utf8')});
  }
  if(url.pathname === '/v1/opportunity-alerts/status') {
   calls.push(route.request().method());
   const body = JSON.stringify(response), failed = fail, wait = delay;
   if(wait) await new Promise(resolve=>setTimeout(resolve, wait));
   return route.fulfill({status:failed?503:200,contentType:'application/json',body});
  }
  return route.fulfill({status:503,contentType:'application/json',body:'{}'});
 });
 const errors=[]; page.on('pageerror', e=>errors.push(e.message));
 await page.goto('http://nightmerit.test/');
 assert.equal(calls.length,0);
 await page.locator('#alerts-status-open').click();
 await page.waitForFunction(()=>document.querySelector('#alerts-status-summary').textContent.includes('Aucun état'));
 assert.equal(await page.locator('#alerts-status-details').isVisible(),false);
 response = {state:'recent_activity',enabled:true,channel:'disabled',updated_at:'2026-10-08T12:00:00+00:00',last_success_at:'2026-10-08T11:00:00+00:00',notification:{at:'2026-10-08T11:00:01+00:00',status:'DELIVERED',reason:'accepted_by_os'},error:null};
 await page.locator('#alerts-status-refresh').click();
 await page.waitForFunction(()=>document.querySelector('#alerts-status-channel').textContent==='Notifications désactivées');
 assert.match(await page.locator('#alerts-status-enabled').innerText(),/Activées/);
 assert.match(await page.locator('#alerts-status-notification').innerText(),/Acceptée par le système/);
 assert.match(await page.locator('#alerts-status-note').innerText(),/affichage/);
 assert.doesNotMatch(await page.locator('#alerts-status-summary').innerText(),/fonctionne|en cours|actif/i);
 if (process.argv[2]) await page.locator('#alerts-status-dialog').screenshot({path:process.argv[2]});
 response = {...response,state:'stale',error:'cycle_failed'};
 await page.locator('#alerts-status-refresh').click();
 await page.waitForFunction(()=>document.querySelector('#alerts-status-summary').textContent.includes('ancien'));
 assert.match(await page.locator('#alerts-status-action').innerText(),/connexion/);
 fail = true;
 await page.locator('#alerts-status-refresh').click();
 await page.waitForFunction(()=>document.querySelector('#alerts-status-summary').textContent.includes('indisponible'));
 assert.equal(await page.locator('#alerts-status-details').isVisible(),false);
 fail = false; response = {state:'stopped',enabled:false,channel:'windows',updated_at:'2026-10-08T12:00:00+00:00',last_success_at:null,notification:{at:'2026-10-08T12:00:00+00:00',status:'FAILED',reason:'delivery_timeout'},error:'delivery_failed'};
 await page.locator('#alerts-status-refresh').click();
 await page.waitForFunction(()=>document.querySelector('#alerts-status-summary').textContent.includes('Arrêt'));
 assert.match(await page.locator('#alerts-status-action').innerText(),/autorisations/);
 for (const width of [390,1280]) {
  await page.setViewportSize({width,height:900});
  assert.equal(await page.locator('#alerts-status-dialog').evaluate(e=>e.scrollWidth<=e.clientWidth),true);
 }
 // A slow pre-close response must not overwrite a newer reopened dialog.
 delay=500; response={state:'unknown'};
 await page.locator('#alerts-status-refresh').click();
 await page.locator('#alerts-status-close').click();
 delay=0; response={state:'unavailable'};
 await page.locator('#alerts-status-open').click();
 await page.waitForFunction(()=>document.querySelector('#alerts-status-summary').textContent.includes('indisponible'));
 await page.waitForTimeout(650);
 assert.match(await page.locator('#alerts-status-summary').innerText(),/indisponible/);
 assert.equal(calls.every(method=>method==='GET'),true);
 assert.deepEqual(errors,[]);
 await browser.close();
 console.log('Opportunity Alerts status browser: PASS');
})().catch(error=>{console.error(error);process.exit(1);});
