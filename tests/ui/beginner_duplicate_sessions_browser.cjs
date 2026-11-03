// Strictly fictitious profile: exercise two distinct sessions at the same displayed minute.
const {chromium}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
(async()=>{const origin=process.env.NIGHTMERIT_CONDUCTOR_URL||'http://127.0.0.1:18812';const out=process.env.NIGHTMERIT_PROOF_DIR;
const browser=await chromium.launch({headless:true,executablePath:process.env.NIGHTMERIT_TEST_CHROME});try{const page=await browser.newPage();await page.goto(origin);await page.locator('#nav-projects').waitFor();
const before=await(await page.request.get(origin+'/v1/projects/M42/progress')).json();
for(const [url,data] of [
['/v1/executions',{execution_id:'conductor-uncredited-same-minute',mission_id:'mission-1'}],
['/v1/execution-transitions',{execution_id:'conductor-uncredited-same-minute',mission_id:'mission-1',status:'in_progress',actual_start:'2026-09-12T20:20:00Z',actual_end:null,actual_duration:null}],
['/v1/execution-transitions',{execution_id:'conductor-uncredited-same-minute',mission_id:'mission-1',status:'completed',actual_start:'2026-09-12T20:20:00Z',actual_end:'2026-09-12T20:30:00Z',actual_duration:600}]
]){const r=await page.request.post(origin+url,{data});assert.equal(r.status(),200,await r.text());}
await page.locator('#nav-projects').click();await page.getByRole('button',{name:'Ajouter mes photos conservées',exact:true}).click();
await page.waitForFunction(()=>document.querySelector('#photos-choice').options.length>=4);
const labels=await page.locator('#photos-choice option').evaluateAll(es=>es.filter(e=>e.value).map(e=>({id:e.value,label:e.textContent})));
assert.equal(new Set(labels.map(e=>e.label)).size,labels.length);
const credited=labels.find(e=>e.id==='conductor-photos-fictives'),uncredited=labels.find(e=>e.id==='conductor-uncredited-same-minute');
assert.match(credited.label,/Séance 1 sur 2.*Déjà ajouté : 0 h 40/);assert.match(uncredited.label,/Séance 2 sur 2.*Photos à renseigner/);
await page.locator('#photos-choice').selectOption(credited.id);assert.equal(await page.locator('#photos-submit').isVisible(),false);
await page.locator('#photos-close').click();assert.deepEqual(await(await page.request.get(origin+'/v1/projects/M42/progress')).json(),before);
if(out)fs.writeFileSync(path.join(out,'seances-distinctes.json'),JSON.stringify({labels,progress_unchanged:true,fixture_only:true},null,2));console.log('PASS: same-minute sessions have distinct labels, credited entry cannot be added twice, progress unchanged.');
}finally{await browser.close()}})().catch(e=>{console.error(e);process.exit(1)});
