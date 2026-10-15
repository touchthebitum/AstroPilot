const fs=require('fs'),path=require('path'),cp=require('child_process'),assert=require('assert');
const root=process.env.CASE_ROOT, intent=process.env.UI_INTENT;
const candidates=process.platform==='win32'?[`${process.env.PROGRAMFILES}\\Google\\Chrome\\Application\\chrome.exe`,`${process.env['PROGRAMFILES(X86)']}\\Microsoft\\Edge\\Application\\msedge.exe`]:['/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'];
const chrome=[process.env.CHROME_BINARY,...candidates].filter(Boolean).find(fs.existsSync);assert(chrome,'No native Chromium browser');
const profile=path.join(root,'browser-profile');fs.mkdirSync(profile);const log=fs.openSync(path.join(root,'browser.log'),'w');
const child=cp.spawn(chrome,['--headless=new','--disable-gpu','--no-first-run','--no-default-browser-check','--disable-background-networking','--remote-debugging-port=0',`--user-data-dir=${profile}`,'about:blank'],{stdio:['ignore',log,log]});
fs.writeFileSync(path.join(root,'browser-pid.json'),JSON.stringify({pid:child.pid,profile}));
const hardLimit=setTimeout(()=>{if(child.exitCode===null){if(process.platform==='win32')cp.spawnSync('taskkill',['/PID',String(child.pid),'/T','/F']);else child.kill('SIGKILL');}process.exit(1);},150000);
const pause=ms=>new Promise(r=>setTimeout(r,ms));let ws,serial=0,pending=new Map();
async function waitFor(fn,label,ms=90000){const end=Date.now()+ms;while(Date.now()<end){const x=await fn();if(x)return x;await pause(150);}throw Error(`Timeout ${label}`);}
async function send(method,params={}){const id=++serial;return new Promise((resolve,reject)=>{console.log('CDP',method);const timer=setTimeout(()=>{pending.delete(id);reject(Error('CDP timeout '+method));},30000);pending.set(id,{resolve,reject,timer});ws.send(JSON.stringify({id,method,params}));});}
async function evaluate(expression){const r=await send('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});if(r.exceptionDetails)throw Error(JSON.stringify(r.exceptionDetails));return r.result.value;}
(async()=>{
 try{
  await waitFor(()=>fs.existsSync(path.join(profile,'DevToolsActivePort')),'Chrome debugger');const port=fs.readFileSync(path.join(profile,'DevToolsActivePort'),'utf8').split('\n')[0];
  const target=await (await fetch(`http://127.0.0.1:${port}/json/new?about:blank`,{method:'PUT',signal:AbortSignal.timeout(15000)})).json();ws=new WebSocket(target.webSocketDebuggerUrl);await new Promise((r,j)=>{const timer=setTimeout(()=>j(Error('WebSocket open timeout')),15000);ws.onopen=()=>{clearTimeout(timer);r();};ws.onerror=j;});
  ws.onmessage=event=>{const r=JSON.parse(event.data);if(r.id&&pending.has(r.id)){const p=pending.get(r.id);pending.delete(r.id);clearTimeout(p.timer);r.error?p.reject(Error(JSON.stringify(r.error))):p.resolve(r.result);}};
  await send('Page.enable');await send('Runtime.enable');await send('Emulation.setDeviceMetricsOverride',{width:1280,height:1200,deviceScaleFactor:1,mobile:false});await send('Emulation.setTimezoneOverride',{timezoneId:'Europe/Zurich'});
  await send('Page.addScriptToEvaluateOnNewDocument',{source:`const RealDate=Date; window.Date=class extends RealDate {constructor(...args){super(...(args.length?args:['2026-10-14T12:00:00Z']));} static now(){return RealDate.parse('2026-10-14T12:00:00Z');}};window.__qualificationTraffic=[];const realFetch=window.fetch.bind(window);window.fetch=async(...args)=>{const response=await realFetch(...args);if(['POST','PUT'].includes(args[1]?.method)){const body=await response.clone().json().catch(()=>null);window.__qualificationTraffic.push({url:String(args[0]),request:JSON.parse(args[1].body||'null'),http:response.status,body});}return response;};`});
  await send('Page.navigate',{url:'http://127.0.0.1:8000/'});
  await waitFor(()=>evaluate(`Boolean(document.querySelector('#availability-step')&&!document.querySelector('#availability-step').hidden)`),'availability UI');
  await evaluate(`document.querySelector('input[name="availability-mode"][value="fixed_window"]').click();document.querySelector('#availability-start').value='2026-10-16T00:30';document.querySelector('#availability-end').value='2026-10-16T03:30';document.querySelector('#request-recommendation').click();true`);
  const prepared=await waitFor(()=>evaluate(`window.__qualificationTraffic.find(x=>x.url==='/v1/tonight')`),'Tonight response');assert.equal(prepared.http,200);assert.equal(prepared.body.night_date,'2026-10-15');if(intent!=='site_changed')assert(prepared.body.viable_acquisition_intent_ids.includes(intent));
  const requestedNightText=await evaluate(`document.querySelector('#night-date').textContent`);assert(/15/.test(requestedNightText),requestedNightText);
  if(intent==='site_changed'){
   await evaluate(`document.querySelector('#edit-configuration').click();document.querySelector('#site-latitude').value='46.9';document.querySelector('#site-next').click();document.querySelector('#equipment-next').click();document.querySelector('#save-configuration').click();true`);
   const changed=await waitFor(()=>evaluate(`window.__qualificationTraffic.find(x=>x.url==='/v1/configuration')`),'configuration save');assert.equal(changed.http,200,JSON.stringify(changed));
   await waitFor(()=>evaluate(`Boolean(!document.querySelector('#availability-step').hidden)`),'availability after site change');
   assert.equal(await evaluate(`window.__qualificationTraffic.filter(x=>x.url==='/v1/decision-selections').length`),0);
   assert.equal(await evaluate(`state.currentDecision===null || state.decision===null`),true);
   const screenshot=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:true});fs.writeFileSync(path.join(root,'ui.png'),Buffer.from(screenshot.data,'base64'));
   fs.writeFileSync(path.join(root,'browser-result.json'),JSON.stringify({result:'PASS',intent,prepared,changed,old_decision_cleared:true,no_confirmation_sent:true,real_dom_interaction:true},null,2));return;
  }
  await waitFor(()=>evaluate(`Boolean(document.querySelector('#primary-intent-choice select'))`),'intent selector');
  await evaluate(`const s=document.querySelector('#primary-intent-choice select');s.value=${JSON.stringify(intent)};s.dispatchEvent(new Event('change',{bubbles:true}));document.querySelector('#open-mission').click();true`);
  const accepted=await waitFor(()=>evaluate(`window.__qualificationTraffic.find(x=>x.url==='/v1/decision-selections')`),'confirmation');assert.equal(accepted.http,200,JSON.stringify(accepted));assert.equal(accepted.body.status,'accepted');assert.equal(accepted.body.selected_acquisition_intent_id,intent);assert.equal(accepted.body.mission.selected_filter.source,'authorized_optical_profile');
  await waitFor(()=>evaluate(`Boolean(document.querySelector('#mission-filter')?.textContent.includes(${JSON.stringify(intent==='ou4_oiii'?'OIII':'Ha')}))`),'rendered mission filter',15000);
  await evaluate("document.querySelector('#mission-filter').scrollIntoView({block:'center'});true");const text=await evaluate('document.body.innerText');const screenshot=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:true});fs.writeFileSync(path.join(root,'ui.png'),Buffer.from(screenshot.data,'base64'));fs.writeFileSync(path.join(root,'ui.txt'),text);
  fs.writeFileSync(path.join(root,'browser-result.json'),JSON.stringify({result:'PASS',browser:chrome,intent,prepared,accepted,ui_text:text,requested_night_text:requestedNightText,real_dom_interaction:true,backend_response_replaced:false,clock_fixture:'2026-10-14T12:00:00Z',timezone:'Europe/Zurich'},null,2));
 }finally{clearTimeout(hardLimit);if(ws)ws.close();if(process.platform==='win32')cp.spawnSync('taskkill',['/PID',String(child.pid),'/T','/F']);else child.kill('SIGTERM');fs.closeSync(log);}
})().catch(error=>{console.error(error);process.exitCode=1;});
