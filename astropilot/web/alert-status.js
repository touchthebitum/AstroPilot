"use strict";

// Observation only: no business request, configuration write, or OS task control.
(() => {
  const dialog = document.querySelector('#alerts-status-dialog');
  const field = name => document.querySelector(`#alerts-status-${name}`);
  let generation = 0;
  let pending = null;
  const date = value => {
    if (!value) return 'Aucun relevé';
    const parsed = new Date(value);
    return Number.isNaN(parsed.getTime()) ? 'Date indisponible' : parsed.toLocaleString('fr-CH');
  };
  const summaries = {
    unknown: 'Aucun état enregistré pour ce profil.',
    unavailable: 'État des alertes indisponible.',
    stale: 'Le dernier état est ancien : vérifiez le service d’alertes.',
    stopped: 'Arrêt enregistré lors du dernier relevé.',
    recent_activity: 'Une activité récente a été enregistrée.',
  };
  const actions = {
    cycle_failed: 'Le dernier cycle a échoué. Vérifiez votre configuration, votre disponibilité et la connexion Internet, puis consultez les diagnostics du service d’alertes.',
    scheduler_failed: 'Le dernier cycle n’a pas pu être enregistré. Vérifiez l’accès au dossier de données et consultez les diagnostics du service d’alertes.',
    delivery_failed: 'La notification a échoué. Vérifiez les autorisations de notification du système et consultez les diagnostics du service d’alertes.',
    host_failed: 'Le service a signalé une erreur. Consultez ses diagnostics avant de le redémarrer.',
  };
  function render(value) {
    const known = ['recent_activity', 'stale', 'stopped'].includes(value.state);
    field('summary').textContent = summaries[value.state] || summaries.unavailable;
    field('details').hidden = !known;
    field('note').hidden = !known;
    for (const name of ['enabled', 'channel', 'success', 'notification', 'updated']) field(name).textContent = '';
    if (!known) {
      field('action').textContent = value.state === 'unknown'
        ? 'Vérifiez que le service d’alertes utilise ce même profil et une version qui enregistre son état.'
        : 'Réessayez. Si le problème persiste, vérifiez l’accès aux données et consultez les diagnostics du service d’alertes.';
      return;
    }
    field('enabled').textContent = value.enabled ? 'Activées' : 'Désactivées';
    field('channel').textContent = {disabled: 'Notifications désactivées', macos: 'macOS', windows: 'Windows'}[value.channel] || 'Inconnu';
    field('success').textContent = date(value.last_success_at);
    const notification = value.notification;
    field('notification').textContent = notification
      ? `${{DELIVERED:'Acceptée par le système',FAILED:'Échec de notification',SKIPPED:'Notification non envoyée'}[notification.status] || 'Statut inconnu'} — ${date(notification.at)}`
      : 'Aucune notification enregistrée';
    field('updated').textContent = date(value.updated_at);
    field('action').textContent = actions[value.error] || (value.state === 'stale'
      ? 'Vérifiez que le service d’alertes est démarré pour ce profil. Un arrêt forcé peut ne pas laisser de relevé d’arrêt.'
      : value.state === 'stopped' ? 'Si vous souhaitez recevoir des alertes, vérifiez le démarrage du service d’alertes.' : '');
  }
  async function load() {
    const current = ++generation;
    if (pending) pending.abort();
    const controller = new AbortController();
    pending = controller;
    const timeout = setTimeout(() => controller.abort(), 10000);
    field('summary').textContent = 'Lecture de l’état…';
    field('details').hidden = true;
    field('note').hidden = true;
    field('action').textContent = '';
    try {
      const response = await fetch('/v1/opportunity-alerts/status', {method:'GET',cache:'no-store',signal:controller.signal});
      if (!response.ok) throw new Error('status_unavailable');
      const value = await response.json();
      if (current === generation && dialog.open) render(value);
    } catch (_) {
      if (current === generation && dialog.open) render({state:'unavailable'});
    } finally {
      clearTimeout(timeout);
      if (current === generation) pending = null;
    }
  }
  field('open').addEventListener('click', () => {dialog.showModal(); load();});
  field('refresh').addEventListener('click', load);
  field('close').addEventListener('click', () => dialog.close());
  dialog.addEventListener('close', () => {generation++; if (pending) pending.abort(); pending = null;});
})();
