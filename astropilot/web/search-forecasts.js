(() => {
  const list = document.querySelector('#forecast-list');
  const detail = document.querySelector('#forecast-detail');
  const message = document.querySelector('#forecast-message');
  const next = document.querySelector('#forecast-next');
  let cursor = null;
  const node = (tag, text) => { const e = document.createElement(tag); e.textContent = text; return e; };
  const date = (value, zone) => new Intl.DateTimeFormat('fr-CH', {
    timeZone: zone, dateStyle: 'short', timeStyle: 'short'
  }).format(new Date(value));
  async function get(path) {
    const r = await fetch(path, {cache: 'no-store'});
    if (!r.ok) throw new Error('lecture');
    return r.json();
  }
  async function read(id) {
    detail.replaceChildren();
    try {
      const d = await get('/v1/search-forecasts/' + encodeURIComponent(id));
      const t = d.weather.trust, h = d.weather.payload.hourly;
      detail.append(node('h2', d.request.site.name),
        node('p', `Collecte : ${date(t.retrieved_at_utc, t.timezone)} · ${t.timezone} · ${t.provider}`),
        node('p', `Site demandé : ${t.requested_latitude}, ${t.requested_longitude}. Grille météo : ${t.grid_latitude}, ${t.grid_longitude}.`),
        node('p', 'Couverture nuageuse prévue reçue du fournisseur, en %. Les couches ne s’additionnent pas. Ce tableau ne décrit pas une observation du ciel et n’autorise pas un départ.'));
      const a = d.request.parameters.availability;
      if (a) {
        const start = a.start_local || (a.start ? date(a.start, t.timezone) : '');
        const end = a.end_local || (a.end ? date(a.end, t.timezone) : '');
        detail.append(node('p', `Disponibilité : ${start && end ? start + ' → ' + end : 'nuit disponible'} · préparation ${a.preparation_minutes} min · flats ${a.flats_minutes} min.`));
      }
      if (!Array.isArray(h.time) || !h.time.length) {
        detail.append(node('p', 'Aucune série horaire disponible dans cet instantané. Aucun pourcentage n’est reconstitué.'));
        message.textContent = 'Archive relue sans actualisation météo.';
        return;
      }
      const table = node('table', ''), head = node('tr', '');
      for (const label of ['Heure locale', 'Total (%)', 'Bas (%)', 'Moyens (%)', 'Hauts (%)']) head.append(node('th', label));
      const thead = node('thead', ''); thead.append(head); table.append(thead);
      const body = node('tbody', '');
      h.time.forEach((epoch, i) => {
        const row = node('tr', '');
        row.append(node('td', date(epoch * 1000, t.timezone)));
        for (const key of ['cloud_cover', 'cloud_cover_low', 'cloud_cover_mid', 'cloud_cover_high'])
          row.append(node('td', h[key]?.[i] == null ? 'Non disponible' : String(h[key][i])));
        body.append(row);
      });
      table.append(body); detail.append(table);
      message.textContent = 'Prévisions archivées relues. Aucune actualisation météo.';
    } catch (_) { message.textContent = 'Impossible de relire ces prévisions conservées. Aucune nouvelle météo n’a été demandée.'; }
  }
  async function load() {
    next.disabled = true;
    try {
      const page = await get('/v1/search-forecasts?limit=20' + (cursor ? '&before=' + encodeURIComponent(cursor) : ''));
      for (const item of page.items) {
        const t = item.weather_trust;
        const button = node('button', `${item.site.name} · collecte ${date(t.retrieved_at_utc, t.timezone)} · ${t.provider}`);
        button.type = 'button'; button.className = 'secondary-button';
        button.addEventListener('click', () => read(item.search_id)); list.append(button);
      }
      cursor = page.next_before; next.hidden = !cursor;
      message.textContent = list.children.length ? 'Choisissez une recherche à relire.' : 'Aucune prévision conservée dans ce profil.';
    } catch (_) { message.textContent = 'Impossible de lire les prévisions conservées. Aucune nouvelle météo n’a été demandée.'; }
    finally { next.disabled = false; }
  }
  next.addEventListener('click', load);
  load();
})();
