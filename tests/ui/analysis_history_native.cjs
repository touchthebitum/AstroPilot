'use strict';
// Synthetic HTTP fixtures + real DOM; no Playwright or external npm dependency.
const fs=require('node:fs'),path=require('node:path'),cp=require('node:child_process');
const http=require('node:http'),assert=require('node:assert/strict');
const {timeHeaders,timeData}=require('./timezone_fixture.cjs');
const {browserEnvironment}=require('../../scripts/ci/night_chain/browser_environment.cjs');
const root=process.env.CASE_ROOT,proof=process.env.CASE_PROOF,chrome=process.env.CHROME_BINARY;
assert(root&&proof&&chrome&&fs.existsSync(chrome));
const web=path.resolve(__dirname,'../../astropilot/web');
const traffic=[],errors=[];let broken=false,empty=false,hold=false,release;
const record={schema:'nightmerit.analysis_history.v1',decision_id:'synthetic-refused-M42',
 created_at_utc:'2026-10-25T19:50:00+00:00',
 request:{selected_project_id:'M42',availability:{mode:'fixed_window',start:'2026-10-25T21:00:00+01:00',end:'2026-10-25T22:30:00+01:00'}},
 result:{status:'no_candidate',decision_id:'synthetic-refused-M42',weather_trust:{timezone:'Europe/Zurich'},
 target_refusal:{catalog_key:'M42',code:'target_below_minimum_altitude',minimum_altitude_deg:30,sample_count:3,
 window_start:'2026-10-25T21:00:00+01:00',window_end:'2026-10-25T22:30:00+01:00'}}};
const server=http.createServer(async(req,res)=>{
 const name=new URL(req.url,'http://127.0.0.1').pathname;traffic.push([req.method,name]);
 for(const [key,value] of Object.entries(timeHeaders))res.setHeader(key,value);
 const json=(body,status=200)=>{res.writeHead(status,{'Content-Type':'application/json'});res.end(JSON.stringify(body));};
 if(name==='/'){res.setHeader('Content-Type','text/html');return res.end(fs.readFileSync(path.join(web,'index.html'),'utf8').replaceAll('__ASTROPILOT_SESSION_TIMING__','').replaceAll('__ASTROPILOT_ASSET_TOKEN__','test'));}
 if(name==='/ui/timezone-data.js'){res.setHeader('Content-Type','text/javascript');return res.end(timeData);}
 const file={'/ui/timezone-authority.js':'timezone-authority.js','/ui/app.js':'app.js','/ui/styles.css':'styles.css'}[name];
 if(file){res.setHeader('Content-Type',file.endsWith('.js')?'text/javascript':'text/css');return res.end(fs.readFileSync(path.join(web,file)));}
 if(name==='/v1/analysis-history'){if(hold)await new Promise(r=>release=r);return json({items:empty?[]:[record],next_before:null},broken?503:200);}
 json({},503);
});
let child,ws,serial=0;const pending=new Map();
const pause=ms=>new Promise(r=>setTimeout(r,ms));
async function waitFor(fn,label){const end=Date.now()+30000;while(Date.now()<end){const result=await fn();if(result)return result;await pause(100);}throw Error('Timeout: '+label);}
function send(method,params={}){const id=++serial;return new Promise((resolve,reject)=>{const timer=setTimeout(()=>{pending.delete(id);reject(Error('CDP timeout '+method));},15000);pending.set(id,{resolve,reject,timer});ws.send(JSON.stringify({id,method,params}));});}
async function evaluate(fn,arg){const result=await send('Runtime.evaluate',{expression:'('+fn.toString()+')('+JSON.stringify(arg)+')',awaitPromise:true,returnByValue:true});if(result.exceptionDetails)throw Error(JSON.stringify(result.exceptionDetails));return result.result.value;}
async function click(selector){await evaluate(selector=>document.querySelector(selector).click(),selector);}
async function stop(){if(ws)ws.close();for(const entry of pending.values())clearTimeout(entry.timer);if(child&&child.exitCode===null&&child.signalCode===null){if(process.platform==='win32')cp.spawnSync('taskkill',['/PID',String(child.pid),'/T','/F'],{timeout:10000});else child.kill('SIGTERM');await waitFor(()=>child.exitCode!==null||child.signalCode!==null,'browser stop');}server.close();}
const deadline=setTimeout(()=>{console.error('Analysis browser deadline');stop().finally(()=>process.exit(1));},120000);
(async()=>{
 try{
  await new Promise(r=>server.listen(0,'127.0.0.1',r));
  const url='http://127.0.0.1:'+server.address().port;
  const profile=path.join(root,'browser-profile');fs.mkdirSync(profile);
  const log=fs.openSync(path.join(proof,'browser.log'),'w');
  child=cp.spawn(chrome,['--headless=new','--disable-gpu','--no-first-run','--no-default-browser-check',
   '--disable-background-networking','--remote-debugging-port=0','--user-data-dir='+profile,'about:blank'],
   {stdio:['ignore',log,log],env:browserEnvironment(process.env)});
  let spawnError;child.on('error',e=>spawnError=e);
  await waitFor(()=>{if(spawnError)throw spawnError;return fs.existsSync(path.join(profile,'DevToolsActivePort'));},'debugger');
  const port=fs.readFileSync(path.join(profile,'DevToolsActivePort'),'utf8').split('\n')[0];
  const tab=await(await fetch('http://127.0.0.1:'+port+'/json/new?about:blank',{method:'PUT'})).json();
  ws=new WebSocket(tab.webSocketDebuggerUrl);
  await new Promise((resolve,reject)=>{ws.onopen=resolve;ws.onerror=reject;});
  ws.onmessage=event=>{const message=JSON.parse(event.data);if(message.id&&pending.has(message.id)){const p=pending.get(message.id);pending.delete(message.id);clearTimeout(p.timer);message.error?p.reject(Error(JSON.stringify(message.error))):p.resolve(message.result);}if(message.method==='Runtime.exceptionThrown')errors.push(message.params);};
  await send('Runtime.enable');await send('Page.enable');
  for(const mode of ['simple','pro'])for(const width of [390,1280]){
   await send('Emulation.setDeviceMetricsOverride',{width,height:900,deviceScaleFactor:1,mobile:false});
   await evaluate(()=>{window.__analysisBeforeReload=true;});
   await send('Page.navigate',{url});
   await waitFor(()=>evaluate(()=>!window.__analysisBeforeReload&&typeof state!=='undefined'&&state.view==='configuration_error'),'page ready');
   await evaluate(({mode,payload})=>{applyUiMode(mode);state.selectedProjectId='M42';state.currentDecision={decision_id:'live-sentinel'};showTonightUnavailable(payload);},{mode,payload:record.result});
   assert.match(await evaluate(()=>document.querySelector('#message-title').textContent),/trop basse/);
   assert.match(await evaluate(()=>document.querySelector('#message-body').textContent),/30°/);
   assert.match(await evaluate(()=>document.querySelector('#message-technical').textContent),/21:00.*22:30/);
   await evaluate(()=>{window.__analysisBeforeReload=true;});
   await send('Page.reload');
   await waitFor(()=>evaluate(()=>!window.__analysisBeforeReload&&typeof state!=='undefined'&&state.view==='configuration_error'),'reload ready');
   await evaluate(()=>{state.currentDecision={decision_id:'live-sentinel'};state.selectedProjectId='live-project';});
   await click('footer [data-open-analysis-history]');
   await waitFor(()=>evaluate(()=>document.querySelector('#analysis-history-list button')!==null),'archive list');
   await click('#analysis-history-list button');
   assert.match(await evaluate(()=>document.querySelector('#analysis-history-detail').textContent),/M42.*trop basse/);
   assert.deepEqual(await evaluate(()=>[state.currentDecision.decision_id,state.selectedProjectId]),['live-sentinel','live-project']);
   assert(await evaluate(()=>{const d=document.querySelector('#analysis-history-dialog');return d.scrollWidth<=d.clientWidth;}),'narrow dialog must fit');
   if(mode==='simple'&&width===1280){const png=await send('Page.captureScreenshot',{format:'png'});fs.writeFileSync(path.join(proof,'ui.png'),Buffer.from(png.data,'base64'));}
   await click('#analysis-history-close');
  }
  record.request.selected_project_id='<img src=x onerror=alert(1)>';record.result.target_refusal.catalog_key=record.request.selected_project_id;
  await click('footer [data-open-analysis-history]');await waitFor(()=>evaluate(()=>!!document.querySelector('#analysis-history-list button')),'inert title');await click('#analysis-history-list button');
  assert.equal(await evaluate(()=>document.querySelectorAll('#analysis-history-dialog img').length),0);
  await click('#analysis-history-close');broken=true;
  await click('footer [data-open-analysis-history]');await waitFor(()=>evaluate(()=>document.querySelector('#analysis-history-message').textContent.includes('ne peuvent pas être lues')),'read failure');
  assert.equal(await evaluate(()=>document.querySelector('#analysis-history-list').childElementCount),0);
  await click('#analysis-history-close');broken=false;empty=true;
  await click('footer [data-open-analysis-history]');await waitFor(()=>evaluate(()=>document.querySelector('#analysis-history-message').textContent.includes('Aucune analyse archivée')),'legacy absence');
  await click('#analysis-history-close');hold=true;empty=false;
  await click('footer [data-open-analysis-history]');await waitFor(()=>!!release,'delayed request');await click('#analysis-history-close');release();await pause(100);
  assert.equal(await evaluate(()=>document.querySelector('#analysis-history-list').childElementCount),0);
  assert.match(await evaluate(()=>normalizeError({status:503},{detail:{code:'analysis_history_unavailable'}})[0]),/Analyse non conservée/);
  assert(traffic.every(([method])=>method==='GET'));assert(!traffic.some(([,p])=>p==='/v1/tonight'));assert.deepEqual(errors,[]);
  fs.writeFileSync(path.join(proof,'result.json'),JSON.stringify({result:'PASS',source_sha:process.env.NIGHT_CHAIN_SOURCE_SHA||null,real_browser:true,reload_reread:true,read_only:true,simple_pro:true,widths:[390,1280],no_html_injection:true,stale_read_ignored:true,traffic},null,2));
  console.log('Analysis history browser PASS');
 }finally{clearTimeout(deadline);await stop();}
})().catch(e=>{console.error(e);process.exitCode=1;});
