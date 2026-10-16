"""Read-only browser observations; normalize text, preserve original bytes on restore."""
def instrument_browser(original: bytes, version: str) -> str:
    text=original.decode('utf-8').replace('\r\n','\n')
    anchor="  fs.writeFileSync(path.join(proof, 'browser-result.json'), JSON.stringify({"
    assert text.count(anchor)==1
    observation='''  const timeAuthorityAudit = await evaluate(`({
      id:NightMeritTime.id, version:NightMeritTime.version,
      winnipegClock:clock('2026-11-02T12:00:00Z','America/Winnipeg'),
      winnipegTask:missionTaskTime('T',{window_start:'2026-11-02T12:00:00Z'},'America/Winnipeg'),
      winnipegLocal:formatDateTimeLocalInZone(new Date('2026-11-02T12:00:00Z'),'America/Winnipeg'),
      winnipegUtc:localDateTimeToUtc('2026-11-02TEXPECTED_CLOCK','America/Winnipeg'),
      winnipegUniqueUtc:localDateTimeToUtc('2026-11-01T01:30','America/Winnipeg'),
      winnipegBoundaryClock:clock('2026-11-01T07:00:00Z','America/Winnipeg'),
      zurichClock:clock('2026-10-15T22:30:00Z','Europe/Zurich'),
      nativeWinnipeg:new Intl.DateTimeFormat('fr-CH',{timeZone:'America/Winnipeg',hour:'2-digit',minute:'2-digit',hour12:false}).format(new Date('2026-11-02T12:00:00Z')),
      userAgent:navigator.userAgent
    })`);
'''.replace('EXPECTED_CLOCK','07:00' if version=='2026.5' else '06:00')
    text=text.replace(anchor,observation+anchor).replace('    ...record, result:','    time_authority_audit:timeAuthorityAudit, ...record, result:')
    navigation="  await send('Page.navigate', {url});"
    assert text.count(navigation)==1
    text=text.replace(navigation,"  const navigation = await send('Page.navigate', {url});\n  fs.writeFileSync(path.join(proof,'navigation.json'),JSON.stringify(navigation));")
    failure="  try { await journey(); }\n  finally {"
    diagnostic="""  try { await journey(); }
  catch (error) {
    try {
      if (ws && ws.readyState === WebSocket.OPEN) {
        const state = await evaluate(`({location:location.href,ready:document.readyState,text:document.body?.innerText?.slice(0,16000),traffic:window.__ciTraffic})`);
        fs.writeFileSync(path.join(proof,'failure-state.json'),JSON.stringify(state,null,2));
        const shot=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:true});
        fs.writeFileSync(path.join(proof,'failure.png'),Buffer.from(shot.data,'base64'));
      }
    } catch (diagnosticError) {console.error('Failure capture',diagnosticError);}
    throw error;
  }
  finally {"""
    assert text.count(failure)==1
    text=text.replace(failure,diagnostic)
    return text
