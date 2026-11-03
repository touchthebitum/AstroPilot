const {chromium} = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

(async () => {
  const origin = process.env.NIGHTMERIT_CONDUCTOR_URL || 'http://127.0.0.1:18811';
  const proof = process.env.NIGHTMERIT_PROOF_DIR;
  const browser = await chromium.launch({headless:true, executablePath:process.env.NIGHTMERIT_TEST_CHROME});
  try {
    const page = await browser.newPage({viewport:{width:1280,height:1000}});
    const errors = [], writes = [];
    page.on('pageerror', e => errors.push(e.message));
    page.on('request', r => { if (['POST','PUT','DELETE'].includes(r.method())) writes.push(new URL(r.url()).pathname); });
    await page.goto(origin);
    await page.locator('#nav-projects').waitFor({state:'visible'});
    await page.locator('#nav-projects').click();
    await page.getByRole('button',{name:'Préparer une séance',exact:true}).click();
    await page.locator('#beginner-choice').waitFor({state:'visible'});
    await page.waitForFunction(()=>document.querySelector('#beginner-project').value==='M42');
    const cases = [];
    for (const width of [320,390,768,1280]) {
      await page.setViewportSize({width,height:1000});
      await page.locator('input[name="availability-mode"][value="fixed_window"]').check();
      await page.locator('#availability-start').fill('2026-11-03T20:00');
      await page.locator('#availability-end').fill('2026-11-03T22:00');
      for (const mode of ['pro','simple']) {
        await page.locator('#ui-mode').selectOption(mode);
        await page.waitForTimeout(80);
        assert.equal(await page.locator('#availability-start').inputValue(),'2026-11-03T20:00');
        assert.equal(await page.locator('#beginner-guide').isVisible(),mode==='simple');
        assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth <= innerWidth),true,'page overflow '+width+' '+mode);
        cases.push({width,mode});
      }
      const helper=page.getByRole('button',{name:'Aide sur toute la nuit',exact:true});
      await helper.click(); await page.locator('#beginner-help').waitFor({state:'visible'});
      await page.keyboard.press('Escape'); await page.locator('#beginner-help').waitFor({state:'hidden'});
      if(proof) await page.screenshot({path:path.join(proof,`preparer-${width}.png`),fullPage:true});
    }
    assert.equal(writes.length,0,'presentation changes must not write');
    await page.locator('#beginner-follow-open').click();
    await page.getByRole('button',{name:'Mes analyses météo',exact:true}).click();
    await page.locator('#analysis-history-dialog').waitFor({state:'visible'});
    await page.locator('#analysis-history-close').click();
    assert.equal(writes.length,0,'reading the journal must not write');
    assert.deepEqual(errors,[]);
    if (proof) fs.writeFileSync(path.join(proof,'presentation.json'),JSON.stringify({cases,errors,writes,api_mocked:false,ui_state_injected:false},null,2));
    console.log('PASS: four widths, both presentations, input preservation, touch/keyboard help, read-only journal.');
  } finally { await browser.close(); }
})().catch(e=>{console.error(e);process.exit(1)});
