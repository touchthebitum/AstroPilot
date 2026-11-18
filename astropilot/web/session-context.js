"use strict";
// Capture the identity at page load; never silently adopt a replacement server.
(() => {
  const binding = globalThis.NightMeritSessionBinding;
  const browser = globalThis.window;
  if (!binding?.session_id || !binding?.storage_scope || !browser?.fetch || !browser.location) return;
  const original = browser.fetch.bind(browser);
  const diagnostic = new Set(['/v1/launcher-context', '/v1/runtime-identity', '/v1/data-context']);
  let storageBlocked = false;
  const scopeKey = 'nightmerit.browser-kit-scope.v1';
  try {
    const previous = localStorage.getItem(scopeKey);
    if (previous && previous !== binding.storage_scope) storageBlocked = true;
    else localStorage.setItem(scopeKey, binding.storage_scope);
  } catch (_) { storageBlocked = true; }
  function changed() {
    const show = () => {
      let notice = document.querySelector('#kit-session-changed-notice');
      if (!notice) { notice = document.createElement('p'); notice.id = 'kit-session-changed-notice'; notice.setAttribute('role', 'alert'); document.body.prepend(notice); }
      notice.textContent = storageBlocked
        ? 'Cette fenêtre contient l’état d’une autre copie ou ne peut pas conserver son identité. Fermez cet onglet et ouvrez la bonne copie avec son propre lanceur ; aucune donnée ne doit être réinitialisée.'
        : 'Cette page appartient à une ancienne session ou à une autre copie. Rechargez-la puis vérifiez le dossier dans « Version et données » avant de continuer.';
    };
    if (document.body) show(); else document.addEventListener('DOMContentLoaded', show, {once:true});
  }
  async function sameServer(signal) {
    const reply = await original(new URL('/v1/launcher-context', browser.location.href), {method:'GET',cache:'no-store',signal});
    if (!reply.ok) return false;
    let identity; try { identity = await reply.json(); } catch (_) { return false; }
    return identity.status === 'managed' && identity.service === 'application' && identity.session_id === binding.session_id;
  }
  if (storageBlocked) changed();
  browser.fetch = async (input, init = {}) => {
    const url = new URL(typeof input === 'string' || input instanceof URL ? input : input.url, browser.location.href);
    if (url.origin !== browser.location.origin || !url.pathname.startsWith('/v1/') || diagnostic.has(url.pathname)) return original(input, init);
    if (storageBlocked) { changed(); throw Error('kit_session_changed'); }
    const method = (init.method || (typeof input === 'object' ? input.method : null) || 'GET').toUpperCase();
    if (!['GET','HEAD','OPTIONS'].includes(method) && !(await sameServer(init.signal))) {
      changed(); throw Error('kit_session_changed');
    }
    const headers = new Headers(init.headers || (typeof input === 'object' ? input.headers : undefined));
    headers.set('X-NightMerit-Session', binding.session_id);
    const response = await original(input, {...init,headers});
    if (response.headers.get('X-NightMerit-Session') !== binding.session_id && !(await sameServer(init.signal))) {
      changed(); throw Error('kit_session_changed');
    }
    if (response.status === 409) {
      let detail;try { detail = (await response.clone().json()).detail; } catch (_) {}
      if (detail?.code === 'kit_session_changed') { changed(); throw Error('kit_session_changed'); }
    }
    return response;
  };
})();
