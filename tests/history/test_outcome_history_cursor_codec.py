"""Signed cursor checks independent of document storage and platform capabilities."""
import base64
import json

import pytest

from decision.services.outcome_history import (
    _CURSOR_ORDER, _decode_cursor, _encode_cursor, OutcomeHistoryInvalidFilter,
)


def test_signed_cursor_roundtrip_and_tampering():
    key = bytes(range(32))
    payload = dict(v=2, dataset='a' * 64, view='b' * 64, offset=1, order=_CURSOR_ORDER)
    token = _encode_cursor(payload, key)
    assert _decode_cursor(token, key) == payload
    changed = dict(payload, offset=0)
    raw = base64.urlsafe_b64encode(json.dumps(changed).encode()).decode().rstrip('=')
    for invalid, signing_key in (
        (raw + '.' + token.split('.')[1], key),
        (token, b'x' * 32),
        (token[:-4], key),
        (_encode_cursor(dict(payload, offset=True), key), key),
    ):
        with pytest.raises(OutcomeHistoryInvalidFilter, match='^invalid_outcome_history_cursor$'):
            _decode_cursor(invalid, signing_key)
