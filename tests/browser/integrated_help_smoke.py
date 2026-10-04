"""Run with Python + Playwright; APIs are mocked, no writes or weather calls.
Set NIGHTMERIT_BROWSER_EXECUTABLE to override the installed browser path.
"""
import os
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2]
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True, executable_path=os.environ.get("NIGHTMERIT_BROWSER_EXECUTABLE", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"))
    for width in [390,1280]:
        page=browser.new_page(viewport={'width':width,'height':800})
        errors=[]
        page.on('pageerror',lambda e:errors.append(str(e)))
        def route(r):
            path=r.request.url.split('http://nightmerit.test',1)[1].split('?',1)[0]
            if path=='/': path='/ui/index.html'
            if path.startswith('/ui/'):
                file=ROOT/'astropilot/web'/path.removeprefix('/ui/')
                r.fulfill(path=str(file))
            else: r.fulfill(status=503,content_type='application/json',body='{"detail":"offline smoke"}')
        page.route('**/*',route)
        page.goto('http://nightmerit.test/')
        page.wait_for_timeout(150)
        page.evaluate("""() => {
          state.currentDecision={id:'retained-decision'};
          state.acceptedMission={id:'retained-mission'};
          state.configurationDraft.projects={draft:'retained'};
          state.pendingAcceptanceAttempt={id:'pending'};
          state.acceptanceBlocked=true;
          state.fieldObservationDraftContext={id:'draft'};
          localStorage.setItem('astropilot.pendingSession','retained');
        }""")
        before=page.evaluate('JSON.stringify(state)')
        page.locator('#help-open').click()
        assert page.locator('#help-dialog').is_visible()
        assert page.locator('#help-close').evaluate('(e)=>e===document.activeElement')
        assert page.locator('[data-help-guide=start]').get_attribute('aria-current')=='page'
        widths=page.locator('.help-navigation button').evaluate_all('(es)=>es.map(e=>e.getBoundingClientRect().width)')
        assert widths[0]>widths[2],widths
        page.locator('[data-help-guide=complete]').click()
        page.locator('#help-content a').nth(10).click()
        assert page.evaluate('document.activeElement.id')=='help-complete-recovery'
        position=page.locator('#help-content').evaluate('(e)=>e.scrollTop')
        assert position>0
        page.select_option('#help-mode','pro')
        assert page.locator('html').get_attribute('data-ui-mode')=='pro'
        assert page.locator('#help-content').evaluate('(e)=>e.scrollTop')==position
        assert page.locator('[data-help-guide=complete]').get_attribute('aria-current')=='page'
        for button in page.locator('.help-navigation button').all(): assert button.is_visible()
        for _ in range(20):
            page.keyboard.press('Tab')
            assert page.evaluate('document.querySelector("#help-dialog").contains(document.activeElement)')
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        assert page.locator('#help-dialog').evaluate('(e)=>e.scrollWidth<=e.clientWidth')
        assert page.locator('#help-content').evaluate('(e)=>e.scrollWidth<=e.clientWidth')
        assert page.locator('#help-dialog').evaluate('(e)=>e.getBoundingClientRect().bottom<=innerHeight')
        position=page.locator('#help-content').evaluate('(e)=>e.scrollTop')
        page.keyboard.press('Shift+Tab')
        assert page.evaluate('document.querySelector("#help-dialog").contains(document.activeElement)')
        position=page.locator('#help-content').evaluate('(e)=>e.scrollTop')
        page.keyboard.press('Escape')
        assert not page.locator('#help-dialog').is_visible()
        assert page.locator('#help-open').evaluate('(e)=>e===document.activeElement')
        assert page.evaluate('JSON.stringify(state)')==before
        assert page.locator('#ui-mode').input_value()=='pro'
        page.locator('#help-open').click()
        assert page.locator('#help-content').evaluate('(e)=>e.scrollTop')==position
        page.select_option('#help-mode','simple')
        assert page.locator('#help-content').evaluate('(e)=>e.scrollTop')==position
        page.locator('#help-close').click()
        assert page.evaluate('JSON.stringify(state)')==before
        assert not errors,errors
        print(f'{width}: Simple/Pro, section+scroll, state, Escape, focus, Tab, overflow PASS')
        page.close()
    browser.close()
