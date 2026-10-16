"use strict";
// UTC rendering is delegated to Intl for language only. Site rules come from Python.
(() => {
  const data = globalThis.NightMeritTimeData;
  if (!data || data.schema !== 1 || !data.id) throw Error('time_authority_unavailable');
  const own = (o, k) => Object.prototype.hasOwnProperty.call(o, k);
  const millis = (year, month, day, seconds = 0) => {
    const d = new Date(0); d.setUTCFullYear(year, month - 1, day); d.setUTCHours(0,0,0,0);
    return d.getTime() + seconds * 1000;
  };
  function ruleAt(rule, year, previousOffset, standard) {
    let wall;
    if (rule.kind === 'M') {
      const first = new Date(millis(year, rule.month, 1)).getUTCDay();
      let day = 1 + (rule.weekday - first + 7) % 7 + (rule.week - 1) * 7;
      if (rule.week === 5 && new Date(millis(year, rule.month, day)).getUTCMonth() !== rule.month - 1) day -= 7;
      wall = millis(year, rule.month, day, rule.seconds);
    } else {
      const leap = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
      const day = rule.kind === 'J' ? rule.day - 1 + (leap && rule.day >= 60 ? 1 : 0) : rule.day;
      wall = millis(year, 1, 1, day * 86400 + rule.seconds);
    }
    const offset = 'ugz'.includes(rule.basis) ? 0 : rule.basis === 's' ? standard : previousOffset;
    return wall - offset * 1000;
  }
  function offsetAt(zone, ms) {
    if (!Number.isFinite(ms) || !own(data.zones, zone)) throw Error('unsupported_site_timezone');
    const rule = data.rules[data.zones[zone]], ts = rule.transitions;
    const future = rule.future;
    if (future && (!ts.length || ms / 1000 > ts[ts.length - 1][0])) {
      if (!future.start) return future.standard;
      const year = new Date(ms).getUTCFullYear();
      let latest = -Infinity, offset = future.standard;
      for (const y of [year - 1, year, year + 1]) {
        for (const [when, value] of [
          [ruleAt(future.start, y, future.standard, future.standard), future.daylight],
          [ruleAt(future.end, y, future.daylight, future.standard), future.standard],
        ]) if (when <= ms && when > latest) { latest = when; offset = value; }
      }
      return offset;
    }
    let lo = 0, hi = ts.length;
    while (lo < hi) {const mid = (lo + hi) >> 1; if (ts[mid][0] <= ms / 1000) lo = mid + 1; else hi = mid;}
    return lo ? ts[lo - 1][1] : rule.initial;
  }
  function offsetLabel(offset) {
    if (!offset) return 'UTC';
    const value = Math.abs(offset), h = Math.floor(value / 3600), m = Math.floor(value % 3600 / 60), s = value % 60;
    return `UTC${offset < 0 ? '−' : '+'}${h}${m || s ? ':' + String(m).padStart(2,'0') : ''}${s ? ':' + String(s).padStart(2,'0') : ''}`;
  }
  class DateTimeFormat {
    constructor(locales, options = {}) {
      const zone = options.timeZone;
      if (zone && !own(data.zones, zone)) throw Error('unsupported_site_timezone');
      this.zone = zone;
      this.native = new Intl.DateTimeFormat(locales, {...options, ...(zone ? {timeZone:'UTC'} : {})});
    }
    formatToParts(value) {
      const date = value === undefined ? new Date() : new Date(value);
      const offset = this.zone ? offsetAt(this.zone, date.getTime()) : 0;
      const shifted = this.zone ? new Date(date.getTime() + offset * 1000) : date;
      return this.native.formatToParts(shifted).map(part => part.type === 'timeZoneName' && this.zone
        ? {...part, value:offsetLabel(offset)} : part);
    }
    format(value) {return this.formatToParts(value).map(p => p.value).join('');}
    resolvedOptions() {return {...this.native.resolvedOptions(), ...(this.zone ? {timeZone:this.zone} : {})};}
  }
  function stop(message) {
    const p = document.createElement('p'); p.setAttribute('role','alert'); p.textContent = message;
    document.body.prepend(p);
    document.querySelectorAll('button,input,select,textarea').forEach(el => {el.disabled = true;});
  }
  globalThis.NightMeritTime = Object.freeze({id:data.id, version:data.package_version,
    ianaVersion:data.iana_version, DateTimeFormat, offsetAt});
  if (typeof window !== 'undefined' && window.fetch && window.location) {
    const original = window.fetch.bind(window);
    window.fetch = async (input, init = {}) => {
      const url = new URL(typeof input === 'string' || input instanceof URL ? input : input.url, window.location.href);
      const api = url.origin === window.location.origin && url.pathname.startsWith('/v1/');
      if (!api) return original(input, init);
      const headers = new Headers(init.headers || (typeof input === 'object' ? input.headers : undefined));
      headers.set('X-NightMerit-Time-Authority', data.id);
      const response = await original(input, {...init, headers});
      if (response.headers.get('X-NightMerit-Time-Authority') !== data.id) {
        stop('Les règles d’heure ont changé ou sont indisponibles. Rechargez avant de continuer.');
        throw Error('time_authority_changed');
      }
      return response;
    };
  }
})();
