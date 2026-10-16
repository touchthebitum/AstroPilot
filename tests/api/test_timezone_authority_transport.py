"""Fail closed before stale-browser writes; do not access any real profile."""
import json

from fastapi.testclient import TestClient

from astropilot.app import create_app
from decision.timezone_authority import identity
from tests.architecture.test_timezone_authority import node


def client():
    return TestClient(create_app(service_factory=lambda: object(),
                                 profile_provider=lambda: {},
                                 weather_provider=lambda lat,lon: object()))


def test_timezone_assets_and_api_share_identity():
    c = client()
    response = c.get('/ui/timezone-data.js')
    assert response.status_code == 200
    assert response.headers['cache-control'] == 'no-store'
    data = json.loads(response.text.removeprefix('globalThis.NightMeritTimeData=').removesuffix(';'))
    assert data['id'] == identity()
    page = c.get('/').text
    assert page.index('/ui/timezone-data.js') < page.index('/ui/timezone-authority.js') < page.index('/ui/app.js')
    assert c.get('/ui/timezone-authority.js').status_code == 200
    assert c.get('/v1/missing').headers['X-NightMerit-Time-Authority'] == identity()


def test_stale_or_missing_browser_identity_prevents_handler_and_preserves_bytes(tmp_path):
    c = client()
    fixture = tmp_path/'isolated-profile.json'
    fixture.write_bytes(b'{"credit": 105, "sessions": ["ha", "oiii"]}')
    before = fixture.read_bytes()
    calls = []
    @c.app.post('/v1/time-authority-probe')
    def probe():
        calls.append('write')
        return {'ok':True}
    for supplied in ({}, {'X-NightMerit-Time-Authority':'stale'}):
        r = c.post('/v1/time-authority-probe',headers={'Origin':'http://testserver',**supplied},json={})
        assert r.status_code == 409
        assert r.json()['detail']['code'] == 'time_authority_changed'
        assert fixture.read_bytes() == before
        assert not calls
    assert c.get('/v1/missing',headers={'X-NightMerit-Time-Authority':'stale'}).status_code == 409
    r = c.post('/v1/time-authority-probe',headers={'Origin':'http://testserver','X-NightMerit-Time-Authority':identity()},json={})
    assert r.status_code == 200 and calls == ['write']
    # Non-browser integrations retain their API contract.
    assert c.post('/v1/time-authority-probe',json={}).status_code == 200


def test_authority_unavailable_has_no_fallback(monkeypatch):
    import decision.timezone_authority as authority
    def broken(): raise ValueError('unsupported data')
    monkeypatch.setattr(authority,'bundle_json',broken)
    monkeypatch.setattr(authority,'identity',broken)
    c = client()
    assert c.get('/ui/timezone-data.js').status_code == 503
    assert c.post('/v1/time-authority-probe',json={}).status_code == 503


def test_browser_transport_marks_requests_and_stops_after_authority_change():
    # Library is reloaded after constructing a minimal browser transport.
    from pathlib import Path
    library=(Path(__file__).resolve().parents[2]/'astropilot/web/timezone-authority.js').read_text(encoding='utf-8')
    node('''
const assert=require('node:assert/strict');
const controls=[{disabled:false}];const notices=[];let calls=[];
globalThis.document={createElement:()=>({setAttribute(){}}),body:{prepend:p=>notices.push(p)},querySelectorAll:()=>controls};
let responseId=NightMeritTime.id;
globalThis.window={location:new URL('http://localhost/'),fetch:async(input,init)=>{
 calls.push({input,init});return {headers:new Headers({'X-NightMerit-Time-Authority':responseId})};}};
'''+library+'''
(async()=>{
 await window.fetch('/v1/tonight');
 assert.equal(calls[0].init.headers.get('X-NightMerit-Time-Authority'),NightMeritTime.id);
 responseId='new-rules';
 await assert.rejects(window.fetch('/v1/executions',{method:'POST'}),/time_authority_changed/);
 assert(controls.every(el=>el.disabled));assert.match(notices[0].textContent,/Rechargez/);
 await window.fetch('/ui/app.js');assert.equal(calls[2].init.headers,undefined);
})().catch(e=>{console.error(e);process.exitCode=1});
''')


def test_guardian_protocol_errors_keep_the_current_authority():
    c = client()
    response = c.post('/v1/executions/example/guardian-renewal',content='invalid',
                      headers={'content-type':'text/plain','X-NightMerit-Time-Authority':identity()})
    assert response.status_code == 422
    assert response.headers['X-NightMerit-Time-Authority'] == identity()
