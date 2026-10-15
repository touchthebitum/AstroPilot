const fs=require('fs'),path=require('path'),cp=require('child_process');
const root=process.env.CASE_ROOT,mode=process.env.DIAGNOSTIC_MODE;
const log=fs.openSync(path.join(root,'chrome.log'),'w'),profile=path.join(root,'profile');fs.mkdirSync(profile);
const args=['--headless=new','--disable-gpu','--no-first-run','--no-default-browser-check','--disable-background-networking','--remote-debugging-port=0',`--user-data-dir=${profile}`,`--log-net-log=${path.join(root,'netlog.json')}`,'about:blank'];if(mode==='no_proxy')args.unshift('--no-proxy-server');
const child=cp.spawn(process.env.CHROME_BINARY,args,{stdio:['ignore',log,log]});
const pause=ms=>new Promise(r=>setTimeout(r,ms));let ws,id=0,pending=new Map(),events=[],rows=[];
async function send(method,params={}){return new Promise((resolve,reject)=>{const key=++id;const timer=setTimeout(()=>{pending.delete(key);reject(Error('Timeout '+method));},8000);pending.set(key,{resolve,reject,timer});ws.send(JSON.stringify({id:key,method,params}));});}
(async()=>{try{
 for(let n=0;n<200&&!fs.existsSync(path.join(profile,'DevToolsActivePort'));n++)await pause(100);
 const port=fs.readFileSync(path.join(profile,'DevToolsActivePort'),'utf8').split('\n')[0];const t=await(await fetch(`http://127.0.0.1:${port}/json/new?about:blank`,{method:'PUT',signal:AbortSignal.timeout(8000)})).json();
 ws=new WebSocket(t.webSocketDebuggerUrl);await new Promise((r,j)=>{const timer=setTimeout(()=>j(Error('WS timeout')),8000);ws.onopen=()=>{clearTimeout(timer);r();};ws.onerror=j;});ws.onmessage=e=>{const r=JSON.parse(e.data);if(r.id&&pending.has(r.id)){const p=pending.get(r.id);pending.delete(r.id);clearTimeout(p.timer);r.error?p.reject(Error(JSON.stringify(r.error))):p.resolve(r.result);}else if(r.method?.startsWith('Network.'))events.push(r);};
 await send('Page.enable');await send('Network.enable');
 for(const url of ['data:text/html,<h1>DATA_OK</h1>','http://127.0.0.1:8000/static','http://localhost:8000/static']){
  try{const result=await send('Page.navigate',{url});await pause(500);const dom=await send('Runtime.evaluate',{expression:'document.body.innerText',returnByValue:true});rows.push({url,navigation:result,text:dom.result.value});}catch(e){rows.push({url,error:String(e)});await send('Page.stopLoading').catch(()=>{});}
 }
}catch(error){rows.push({fatal:String(error)});}finally{fs.writeFileSync(path.join(root,'diagnosis.json'),JSON.stringify({mode,rows,events,isolated_profile:profile},null,2));if(ws)ws.close();if(child.exitCode===null)child.kill('SIGTERM');fs.closeSync(log);}})().catch(e=>{console.error(e);process.exitCode=1;});
