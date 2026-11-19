"use strict";
(() => {
  const identity = globalThis.NightMeritCopyIdentity || {};
  const labels = {personal:'Personnel', fictitious:'Essai fictif'};
  const kind = Object.prototype.hasOwnProperty.call(labels, identity.kind) ? identity.kind : 'unidentified';
  const label = labels[kind] || 'Copie non identifiée';
  function render() {
    if (document.getElementById('copy-identity-banner')) return;
    const style = document.createElement('style');
    style.textContent = `
#copy-identity-banner { position:sticky; top:0; z-index:900; display:flex; align-items:center; gap:.7rem; flex-wrap:wrap; width:100%; box-sizing:border-box; margin:0; padding:.55rem max(1rem,env(safe-area-inset-left)); background:#112536; color:#f2f7fc; border-bottom:2px solid #69b8f5; font:14px/1.45 system-ui,sans-serif; }
#copy-identity-banner[data-copy-kind="fictitious"] { background:#302513; border-color:#ffd17a; }
#copy-identity-banner[data-copy-kind="unidentified"] { background:#302323; border-color:#f4aaaa; }
#copy-identity-banner .copy-kind { flex-shrink:0; font-weight:750; }
#copy-identity-banner .copy-name { min-width:0; flex:1 1 12rem; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; font-size:13px; color:#dce6ef; }
#copy-identity-banner .copy-label { font-weight:400; }
`;
    document.head.append(style);
    const banner = document.createElement('aside');
    banner.id = 'copy-identity-banner'; banner.dataset.copyKind = kind;
    banner.setAttribute('role','note'); banner.setAttribute('aria-label','Identification de la copie ouverte');
    const title = document.createElement('span'); title.className = 'copy-kind';
    const prefix = document.createElement('span'); prefix.className = 'copy-label'; prefix.textContent = 'Copie ouverte : ';
    title.append(prefix,document.createTextNode(label)); banner.append(title);
    const name = document.createElement('span'); name.className = 'copy-name';
    name.textContent = typeof identity.name === 'string' && identity.name ? identity.name : 'Utilisez le lanceur de la copie pour l’identifier.';
    name.title = name.textContent; banner.append(name);
    document.body.prepend(banner);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded',render,{once:true}); else render();
})();
