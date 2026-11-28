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
  // Keep the legacy owner's data in place. A different extraction gets its own
  // namespace, including recovery journals, instead of adopting or deleting it.
  const namespaceRoot = 'nightmerit.copy-storage.v1:';
  try {
    const storage = browser.localStorage;
    const previous = storage.getItem(scopeKey);
    if (!previous) storage.setItem(scopeKey, binding.storage_scope);
    const prefix = previous && previous !== binding.storage_scope
      ? `${namespaceRoot}${binding.storage_scope}:` : '';
    const keys = () => Array.from({length:storage.length}, (_, i) => storage.key(i))
      .filter(key => key !== null && (prefix ? key.startsWith(prefix)
        : key !== scopeKey && !key.startsWith(namespaceRoot)));
    globalThis.NightMeritStorageNamespace = prefix;
    globalThis.NightMeritStorage = Object.freeze({
      getItem: key => storage.getItem(prefix + key),
      setItem: (key, value) => storage.setItem(prefix + key, value),
      removeItem: key => storage.removeItem(prefix + key),
      key: index => { const key = keys()[index]; return key === undefined ? null : key.slice(prefix.length); },
      get length() { return keys().length; },
    });
    globalThis.NightMeritStorageEvent = event => {
      if (event.storageArea && event.storageArea !== storage) return null;
      if (event.key === null) return event; // Origin-wide clear still fails closed.
      if (prefix ? !event.key.startsWith(prefix)
          : event.key === scopeKey || event.key.startsWith(namespaceRoot)) return null;
      return {key:event.key.slice(prefix.length), newValue:event.newValue, oldValue:event.oldValue};
    };
  } catch (_) { storageBlocked = true; }
  function changed() {
    const show = () => {
      let notice = document.querySelector('#kit-session-changed-notice');
      if (!notice) { notice = document.createElement('p'); notice.id = 'kit-session-changed-notice'; notice.setAttribute('role', 'alert'); document.body.prepend(notice); }
      notice.textContent = storageBlocked
        ? 'Cette fenêtre ne peut pas conserver son identité dans le navigateur. Fermez cet onglet et ouvrez la bonne copie avec son propre lanceur ; aucune donnée ne doit être réinitialisée.'
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
