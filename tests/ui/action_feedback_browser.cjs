// Presentation regression only: production UI files, no server/profile writes.
const {chromium}=require('playwright'),fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {timeHeaders,timeData}=require('./timezone_fixture.cjs');
(async()=>{const web=path.resolve(__dirname,'../../astropilot/web'),out=process.env.NIGHTMERIT_PROOF_DIR;
 const browser=await chromium.launch({headless:true,executablePath:process.env.NIGHTMERIT_TEST_CHROME});
 try{const page=await browser.newPage(),writes=[],errors=[];
 page.on('request',r=>{if(r.method()!=='GET')writes.push(r.url())});page.on('pageerror',e=>errors.push(e.message));
 await page.route('http://127.0.0.1:18479/**',route=>{
   const url=new URL(route.request().url());
   if(url.pathname==='/')return route.fulfill({headers:timeHeaders,contentType:'text/html',body:fs.readFileSync(path.join(web,'index.html'),'utf8').replaceAll('__ASTROPILOT_ASSET_TOKEN__','review').replaceAll('__ASTROPILOT_SESSION_TIMING__','')});
   if(url.pathname==='/ui/timezone-data.js')return route.fulfill({headers:timeHeaders,contentType:'text/javascript',body:timeData});
   const file={'/ui/styles.css':'styles.css','/ui/app.js':'app.js','/ui/timezone-authority.js':'timezone-authority.js'}[url.pathname];
   return file?route.fulfill({headers:timeHeaders,contentType:file.endsWith('.css')?'text/css':'text/javascript',body:fs.readFileSync(path.join(web,file),'utf8')}):route.fulfill({headers:timeHeaders,status:503,json:{}});
 });
 await page.goto('http://127.0.0.1:18479/');await page.waitForFunction(()=>typeof observationMessage==='function'&&typeof applyUiMode==='function');
 const results=[];
 for(const mode of ['simple','pro'])for(const width of [390,768,1280,1600]){
   await page.setViewportSize({width,height:950});
   await page.evaluate(mode=>{applyUiMode(mode);const dialog=document.querySelector('#field-observation-dialog');if(!dialog.open)dialog.showModal()},mode);
   for(const kind of ['success','error','info']){
     const message={success:'Observation enregistrée.',error:'Enregistrement impossible. Votre saisie est conservée ; réessayez.',info:'Choisissez les conditions observées.'}[kind];
     const result=await page.evaluate(({kind,message})=>{
       observationMessage(message,{success:kind==='success',error:kind==='error'});
       const el=document.querySelector('#observation-status'),style=getComputedStyle(el),icon=getComputedStyle(el,'::before'),box=el.getBoundingClientRect();
       if(kind!=='success')el.scrollIntoView({block:'nearest'});
       return {text:el.textContent,success:el.classList.contains('confirmation-success'),error:el.classList.contains('observation-error'),background:style.backgroundColor,font:style.fontSize,icon:icon.content,role:el.getAttribute('role'),atomic:el.getAttribute('aria-atomic'),fits:box.width<=window.innerWidth&&el.scrollWidth<=el.clientWidth};
     },{kind,message});
     assert.equal(result.text,message);assert.equal(result.success,kind==='success');assert.equal(result.error,kind==='error');assert.equal(result.role,'status');assert.equal(result.atomic,'true');assert.equal(result.font,'16px');assert.ok(result.fits);
     assert.equal(result.background,{success:'rgb(17, 59, 50)',error:'rgb(70, 28, 35)',info:'rgb(19, 44, 64)'}[kind]);
     assert.ok(result.icon.includes({success:'✓',error:'!',info:'i'}[kind]));
     if(kind==='success'){const visible=await page.locator('#observation-status').boundingBox();assert.ok(visible.y>=0&&visible.y+visible.height<=950)}
     if(out&&mode==='simple'&&[390,1280].includes(width)&&kind!=='info')await page.screenshot({path:path.join(out,`${kind}-${width}.png`)});
     results.push({mode,width,kind,...result});
   }
 }
 await page.evaluate(()=>{observationMessage('');sessionMessage('Cette durée a été ajoutée à votre projet.',{success:true})});
 assert.equal(await page.locator('#observation-status').isVisible(),false);
 assert.equal(await page.locator('#session-status').evaluate(el=>el.classList.contains('confirmation-success')),true);
 await page.evaluate(()=>sessionMessage('Lecture impossible.',{error:true}));
 assert.equal(await page.locator('#session-status').evaluate(el=>el.classList.contains('error')&&!el.classList.contains('confirmation-success')),true);
 assert.deepEqual(writes,[]);assert.deepEqual(errors,[]);
 if(out)fs.writeFileSync(path.join(out,'feedback-browser.json'),JSON.stringify({result:'PASS',cases:results.length,results,writes,errors,http_mocked:true,profile_used:false},null,2));
 console.log('PASS: 24 feedback states, Simple/Pro four widths; red errors, distinct success, automatic visibility, reset, no writes.');
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exit(1)});
