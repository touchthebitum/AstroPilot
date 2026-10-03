"""Bounded, read-only catalogue of persisted forecast evidence.

Retrieval time is deliberately not presented as decision creation time.
The hardened file reader has the same fail-closed platform contract as History.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import math
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from astropilot.outcome_history_reader import (
    FileOutcomeHistoryReader, OutcomeHistoryUnavailable, _MAX_DOCUMENT_BYTES,
    OutcomeHistoryDocumentTooLarge, _require_secure_fs_capabilities,
)
from decision.weather.decision_forecast_evidence_persistence import (
    deserialize_decision_forecast_evidence, DecisionForecastEvidencePersistenceError,
)


class RecentDecisionsInvalidFilter(ValueError):
    pass


class RecentDecisionsDatasetChanged(ValueError):
    pass


class RecentDecisionsUnavailable(RuntimeError):
    pass


class FileRecentDecisionReader:
    MAX_DOCUMENTS = 512
    MAX_TOTAL_BYTES = 32 * 1024 * 1024
    KIND = "decision_forecast_evidence"

    def __init__(self, directory: Path, *, cursor_key: bytes):
        if type(cursor_key) is not bytes or len(cursor_key) < 32:
            raise ValueError("recent_decisions_cursor_key_required")
        self._cursor_key = cursor_key
        # Reuse History's existing no-follow, regular-file, bounded read boundary.
        self._files = FileOutcomeHistoryReader(directory)

    def _inventory(self):
        try:
            fd = self._files._directory_fd(self.KIND)
        except FileNotFoundError:
            return []
        try:
            names = []
            with os.scandir(fd) as entries:
                for entry in entries:
                    if entry.name.endswith(".json"):
                        names.append(entry.name)
                        if len(names) > self.MAX_DOCUMENTS:
                            raise RecentDecisionsUnavailable("recent_decisions_scan_limit")
            return sorted(names)
        finally:
            os.close(fd)

    def _snapshot(self):
        names = self._inventory()
        documents = []
        digest = hashlib.sha256()
        total = 0
        for name in names:
            remaining = self.MAX_TOTAL_BYTES - total
            try:
                raw = self._files._read_bytes(
                    self.KIND, name, remaining_total_budget=remaining)
            except OutcomeHistoryDocumentTooLarge as error:
                if remaining <= _MAX_DOCUMENT_BYTES:
                    raise RecentDecisionsUnavailable("recent_decisions_scan_limit") from error
                raise
            total += len(raw)
            if total > self.MAX_TOTAL_BYTES:
                raise RecentDecisionsUnavailable("recent_decisions_scan_limit")
            digest.update(name.encode())
            digest.update(b"\0")
            digest.update(hashlib.sha256(raw).digest())
            documents.append((name[:-5], raw))
        if names != self._inventory():
            raise RecentDecisionsDatasetChanged("recent_decisions_dataset_changed")
        return digest.hexdigest(), documents

    @staticmethod
    def _unique_fields(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError("duplicate_cursor_field")
            value[key] = item
        return value

    @staticmethod
    def _instant(value):
        if not isinstance(value, str) or len(value) > 64:
            raise RecentDecisionsInvalidFilter("invalid_recent_decisions_time_range")
        try:
            instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if instant.utcoffset() is None:
                raise ValueError()
            return instant.astimezone(timezone.utc)
        except (ValueError, OverflowError):
            raise RecentDecisionsInvalidFilter("invalid_recent_decisions_time_range") from None

    def list_recent(self, *, latitude, longitude, retrieved_from, retrieved_to,
                    limit=10, cursor=None):
        if (type(latitude) not in (int, float) or type(longitude) not in (int, float)
                or not math.isfinite(latitude) or not math.isfinite(longitude)
                or not -90 <= latitude <= 90 or not -180 <= longitude <= 180):
            raise RecentDecisionsInvalidFilter("invalid_recent_decisions_site")
        latitude = 0.0 if latitude == 0.0 else float(latitude)
        longitude = 0.0 if longitude == 0.0 else float(longitude)
        start, end = self._instant(retrieved_from), self._instant(retrieved_to)
        if start > end or end - start > timedelta(days=31):
            raise RecentDecisionsInvalidFilter("invalid_recent_decisions_time_range")
        if type(limit) is not int or not 1 <= limit <= 50:
            raise RecentDecisionsInvalidFilter("invalid_recent_decisions_limit")
        query = hashlib.sha256(json.dumps(
            [float(latitude), float(longitude), start.isoformat(), end.isoformat(), limit],
            separators=(",", ":"), allow_nan=False,
        ).encode()).hexdigest()
        offset = 0
        expected_fingerprint = None
        if cursor is not None:
            try:
                if not isinstance(cursor, str) or len(cursor) > 512:
                    raise ValueError()
                encoded, signature = cursor.split(".")
                expected_signature = hmac.new(self._cursor_key, b"recent-decisions-v1\0" + encoded.encode(), hashlib.sha256).hexdigest()
                if not hmac.compare_digest(signature, expected_signature):
                    raise ValueError()
                value = json.loads(base64.b64decode(encoded, altchars=b"-_", validate=True),
                                   object_pairs_hook=self._unique_fields)
                if (type(value) is not dict or set(value) != {"version", "query", "fingerprint", "offset"}
                        or type(value["version"]) is not int or value["version"] != 1 or value["query"] != query
                        or type(value["offset"]) is not int or not 1 <= value["offset"] <= self.MAX_DOCUMENTS
                        or type(value["fingerprint"]) is not str or re.fullmatch(r"[0-9a-f]{64}", value["fingerprint"]) is None):
                    raise ValueError()
                offset, expected_fingerprint = value["offset"], value["fingerprint"]
            except (ValueError, TypeError, KeyError, UnicodeError):
                raise RecentDecisionsInvalidFilter("invalid_recent_decisions_cursor") from None
        try:
            _require_secure_fs_capabilities()
            fingerprint, documents = self._snapshot()
        except (OSError, OutcomeHistoryUnavailable, OutcomeHistoryDocumentTooLarge,
                DecisionForecastEvidencePersistenceError) as error:
            raise RecentDecisionsUnavailable("recent_decisions_unavailable") from error
        if expected_fingerprint is not None and expected_fingerprint != fingerprint:
            raise RecentDecisionsDatasetChanged("recent_decisions_dataset_changed")
        items, diagnostics = [], []
        for decision_id, raw in documents:
            try:
                evidence = deserialize_decision_forecast_evidence(raw.decode("utf-8"), decision_id=decision_id)
            except (ValueError, UnicodeError, RecursionError, OverflowError):
                diagnostics.append({"decision_id": decision_id, "code": "decision_evidence_invalid"})
                continue
            points = evidence.forecast_points
            if not points:
                diagnostics.append({"decision_id": decision_id, "code": "decision_evidence_empty"})
                continue
            locations = {(p.requested_location.latitude, p.requested_location.longitude) for p in points}
            retrievals = {p.retrieved_at_utc for p in points}
            if len(locations) != 1 or len(retrievals) != 1:
                diagnostics.append({"decision_id": decision_id, "code": "decision_evidence_context_inconsistent"})
                continue
            retrieved = next(iter(retrievals))
            if locations != {(latitude, longitude)} or not start <= retrieved <= end:
                continue
            items.append({
                "decision_id": decision_id, "decision_created_at_utc": None,
                "retrieved_at_utc": retrieved.isoformat(),
                "site": {"latitude": latitude, "longitude": longitude, "name": None,
                         "timezone": None, "site_id": None, "site_revision": None},
                "forecast_from_utc": min(p.forecast_for_utc for p in points).isoformat(),
                "forecast_to_utc": max(p.forecast_for_utc for p in points).isoformat(),
                "variables": sorted({v.variable.value for p in points for v in p.values}),
                "night_date": None, "decision_status": None, "superseded": None,
                "target": None, "acquisition_intent_id": None,
                "selectable_decision_only": True,
            })
        items.sort(key=lambda item: (item["retrieved_at_utc"], item["decision_id"]), reverse=True)
        if offset > len(items):
            raise RecentDecisionsInvalidFilter("invalid_recent_decisions_cursor")
        next_offset = offset + limit
        next_cursor = None
        if next_offset < len(items):
            next_cursor = base64.urlsafe_b64encode(json.dumps({
                "version": 1, "query": query, "fingerprint": fingerprint, "offset": next_offset,
            }, separators=(",", ":")).encode()).decode()
            next_cursor += "." + hmac.new(self._cursor_key, b"recent-decisions-v1\0" + next_cursor.encode(), hashlib.sha256).hexdigest()
        return {"items": items[offset:next_offset], "next_cursor": next_cursor,
                "time_basis": "forecast_retrieved_at_utc", "site_match": "exact_requested_coordinates",
                "comparability_guaranteed": False, "complete": not diagnostics,
                "diagnostics": diagnostics}
