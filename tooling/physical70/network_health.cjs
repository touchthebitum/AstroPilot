'use strict';
const assert = require('node:assert/strict');
(async () => {
  const [port, url] = process.argv.slice(2);
  const targets = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
  const target = targets.find(t => t.type === 'page' && t.url === url);
  assert(target, JSON.stringify(targets));
  const ws = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((resolve,reject)=>{ws.onopen=resolve;ws.onerror=reject;});
  const timer = setTimeout(()=>{console.error('DOM deadline');process.exit(1);},20000);
  let n = 0;
  const pending = new Map();
  ws.onmessage = e => { const m=JSON.parse(e.data);if(pending.has(m.id)){pending.get(m.id)(m);pending.delete(m.id);} };
  const send = (method,params={}) => new Promise(resolve=>{const id=++n;pending.set(id,resolve);ws.send(JSON.stringify({id,method,params}));});
  let text='';
  for(let i=0;i<50;i++){
    const m=await send('Runtime.evaluate',{expression:'document.body.innerText',returnByValue:true});
    text=m.result?.result?.value||'';
    if(text.includes('NIGHTMERIT_NETWORK_PROBE'))break;
    await new Promise(resolve=>setTimeout(resolve,100));
  }
  assert(text.includes('NIGHTMERIT_NETWORK_PROBE'),text);
  console.log(JSON.stringify({dom_ok:true,text}));
  clearTimeout(timer);ws.close();
})().catch(e=>{console.error(e);process.exit(1);});
