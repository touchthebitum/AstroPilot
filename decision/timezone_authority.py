"""One locked IANA source for Python and the browser; no system fallback.

TZif v2/v3, RFC 9636. The browser receives transitions and parsed footer rules,
not a second independently updated timezone database. Unsupported data fails closed.
"""
from functools import lru_cache
from importlib import resources
import hashlib
import json
import re
import struct
import zoneinfo


def configure() -> None:
    # Once, while importing decision, before application zones are constructed.
    import tzdata  # required runtime dependency, including on macOS
    if not tzdata.IANA_VERSION:
        raise RuntimeError("time_authority_unavailable")
    zoneinfo.reset_tzpath(())
    zoneinfo.ZoneInfo.clear_cache()


def _seconds(value: str) -> int:
    sign = -1 if value.startswith('-') else 1
    parts = [int(v) for v in value.lstrip('+-').split(':')]
    if len(parts) > 3 or parts[0] > 167 or any(v > 59 for v in parts[1:]):
        raise ValueError('time_authority_invalid_offset')
    return sign * sum(v * scale for v, scale in zip(parts, (3600, 60, 1)))


def _rule(value: str) -> dict:
    day, _, clock = value.partition('/')
    basis = 'w'
    if clock and clock[-1] in 'wsugz':
        basis, clock = clock[-1], clock[:-1]
    seconds = _seconds(clock) if clock else 7200
    if day.startswith('M'):
        m = re.fullmatch(r'M(\d+)\.(\d+)\.(\d+)', day)
        if not m:
            raise ValueError('time_authority_invalid_rule')
        month, week, weekday = map(int, m.groups())
        if not (1 <= month <= 12 and 1 <= week <= 5 and 0 <= weekday <= 6):
            raise ValueError('time_authority_invalid_rule')
        return dict(kind='M', month=month, week=week, weekday=weekday, seconds=seconds, basis=basis)
    if re.fullmatch(r'J\d+|\d+', day):
        n = int(day.lstrip('J'))
        if not (1 <= n <= 365 if day.startswith('J') else 0 <= n <= 365):
            raise ValueError('time_authority_invalid_rule')
        return dict(kind='J' if day.startswith('J') else 'N', day=n, seconds=seconds, basis=basis)
    raise ValueError('time_authority_invalid_rule')


def _footer(value: str) -> dict | None:
    if not value:
        return None
    name = r'(?:<[A-Za-z0-9+\-]+>|[A-Za-z]{3,})'
    number = r'[+\-]?\d{1,3}(?::\d{1,2}(?::\d{1,2})?)?'
    m = re.fullmatch(rf'{name}({number})(?:{name}({number})?,([^,]+),([^,]+))?', value)
    if not m:
        raise ValueError('time_authority_unsupported_footer')
    std, dst, start, end = m.groups()
    standard = -_seconds(std)
    if start is None:
        return {'standard': standard}
    return dict(standard=standard, daylight=-_seconds(dst) if dst else standard + 3600,
                start=_rule(start), end=_rule(end))


def _decode(data: bytes) -> dict:
    def header(at):
        if data[at:at+4] != b'TZif' or len(data) < at + 44:
            raise ValueError('time_authority_invalid_tzif')
        return struct.unpack('>6I', data[at+20:at+44])
    def size(c, width):
        g, s, leaps, times, types, chars = c
        return (width + 1) * times + 6 * types + chars + (width + 4) * leaps + s + g
    counts = header(0)
    if data[4:5] not in (b'2', b'3', b'4'):
        raise ValueError('time_authority_unsupported_tzif')
    at = 44 + size(counts, 4)
    counts = header(at)
    g, s, leaps, n, k, chars = counts
    if not 0 < k <= 256 or leaps or n > 10000:
        raise ValueError('time_authority_invalid_tzif')
    start = at + 44
    end = start + size(counts, 8)
    if end > len(data):
        raise ValueError('time_authority_invalid_tzif')
    instants = struct.unpack(f'>{n}q', data[start:start+8*n])
    indexes = data[start+8*n:start+9*n]
    types = [struct.unpack('>iBB', data[start+9*n+6*i:start+9*n+6*i+6]) for i in range(k)]
    if any(i >= k for i in indexes) or any(abs(v[0]) > 93600 or v[1] not in (0, 1) for v in types):
        raise ValueError('time_authority_invalid_tzif')
    if any(a >= b for a, b in zip(instants, instants[1:])) or any(abs(v) > 2**53-1 for v in instants):
        raise ValueError('time_authority_invalid_transitions')
    footer = data[end:]
    if not (footer.startswith(b'\n') and footer.endswith(b'\n')):
        raise ValueError('time_authority_invalid_footer')
    return dict(initial=types[0][0], transitions=[[t, types[i][0]] for t, i in zip(instants, indexes)],
                future=_footer(footer[1:-1].decode('ascii')))


@lru_cache(maxsize=1)
def bundle_json() -> str:
    import tzdata
    zones, rules = {}, {}
    for key in resources.files('tzdata').joinpath('zones').read_text(encoding='utf-8').splitlines():
        if not re.fullmatch(r'[A-Za-z0-9_+\-/]+', key) or '..' in key.split('/'):
            raise ValueError('time_authority_invalid_key')
        raw = resources.files('tzdata.zoneinfo').joinpath(*key.split('/')).read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        zones[key] = digest
        if digest not in rules:
            rules[digest] = _decode(raw)
    body = dict(schema=1, package_version=tzdata.__version__, iana_version=tzdata.IANA_VERSION,
                zones=zones, rules=rules)
    encoded = json.dumps(body, separators=(',', ':'), sort_keys=True)
    body['id'] = hashlib.sha256(encoded.encode()).hexdigest()
    return json.dumps(body, separators=(',', ':'), sort_keys=True)


@lru_cache(maxsize=1)
def identity() -> str:
    return json.loads(bundle_json())['id']
