"""Immutable, bounded analysis snapshots. Reading never creates user state."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import stat
import tempfile

from astropilot.durable_file_publication import fsync_directory, cleanup_temporary_files_durably
from astropilot.field_lab_paths import require_user_directory
from astropilot.file_lock import exclusive_file_lock

SCHEMA = "nightmerit.analysis_history.v1"
MAX_DOCUMENT = 1024 * 1024
MAX_RECORDS = 512
MAX_TOTAL = 32 * 1024 * 1024


class AnalysisHistoryError(ValueError):
    pass


def identity(value):
    if (not isinstance(value, str) or re.fullmatch(r"[A-Za-z0-9_-]{1,128}", value) is None
            or value.upper() in {"CON", "PRN", "AUX", "NUL",
                                 *[f"COM{i}" for i in range(1, 10)],
                                 *[f"LPT{i}" for i in range(1, 10)]}):
        raise AnalysisHistoryError("analysis_history_invalid_identity")
    return value


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise AnalysisHistoryError("analysis_history_invalid")
        result[key] = value
    return result


def decode(raw, expected_id):
    from astropilot.app import TonightRequest, TonightResponseModel
    try:
        doc = json.loads(raw, object_pairs_hook=_unique,
                         parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
        if not isinstance(doc, dict) or set(doc) != {"schema", "decision_id", "created_at_utc", "request", "result"}:
            raise ValueError()
        if doc["schema"] != SCHEMA or identity(doc["decision_id"]) != expected_id:
            raise ValueError()
        created = datetime.fromisoformat(doc["created_at_utc"])
        if created.utcoffset() != timezone.utc.utcoffset(created):
            raise ValueError()
        if not isinstance(doc["result"], dict) or set(doc["result"]) - set(TonightResponseModel.model_fields):
            raise ValueError()
        doc["created_at_utc"] = created.astimezone(timezone.utc).isoformat()
        request = TonightRequest.model_validate(doc["request"])
        result = TonightResponseModel.model_validate(doc["result"])
        if result.decision_id != expected_id:
            raise ValueError()
        # Keep a validated transport snapshot, never a serialized Python object.
        doc["request"] = request.model_dump(mode="json", exclude_none=True)
        doc["result"] = result.model_dump(mode="json")
        return doc
    except (ValueError, TypeError, KeyError, UnicodeError, RecursionError, OverflowError) as exc:
        raise AnalysisHistoryError("analysis_history_invalid") from exc


class FileAnalysisHistory:
    def __init__(self, directory):
        self.directory = Path(directory).absolute()

    def _checked(self):
        require_user_directory(self.directory)
        for path in (self.directory, *self.directory.parents):
            if path.is_symlink():
                raise AnalysisHistoryError("analysis_history_unsafe_path")
            if path.exists():
                info = path.lstat()
                if not stat.S_ISDIR(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                    raise AnalysisHistoryError("analysis_history_unsafe_path")
        return self.directory

    def _raw(self, key):
        path = self._checked() / (identity(key) + ".json")
        try:
            before = path.lstat()
        except FileNotFoundError:
            return None
        if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
                or getattr(before, "st_file_attributes", 0) & 0x400 or before.st_size > MAX_DOCUMENT):
            raise AnalysisHistoryError("analysis_history_unsafe_document")
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_BINARY", 0)
                     | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
        try:
            opened = os.fstat(fd)
            signature = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns)
            if signature(before) != signature(opened):
                raise AnalysisHistoryError("analysis_history_changed")
            with os.fdopen(fd, "rb", closefd=False) as stream:
                raw = stream.read(MAX_DOCUMENT + 1)
            if len(raw) > MAX_DOCUMENT or signature(before) != signature(path.lstat()):
                raise AnalysisHistoryError("analysis_history_changed")
            self._checked()
            return raw
        finally:
            os.close(fd)

    def load(self, key):
        raw = self._raw(key)
        return decode(raw, key) if raw is not None else None

    def list_records(self, *, before=None, limit=20):
        root = self._checked()
        if not root.exists():
            return {"items": [], "next_before": None}
        names = []
        for path in root.iterdir():
            if path.name.endswith(".json"):
                names.append(path.stem)
                if len(names) > MAX_RECORDS:
                    raise AnalysisHistoryError("analysis_history_scan_limit")
        records, total = [], 0
        for key in names:
            raw = self._raw(key)
            if raw is None:
                raise AnalysisHistoryError("analysis_history_changed")
            total += len(raw)
            if total > MAX_TOTAL:
                raise AnalysisHistoryError("analysis_history_scan_limit")
            records.append(decode(raw, key))
        records.sort(key=lambda d: (d["created_at_utc"], d["decision_id"]), reverse=True)
        if before is not None:
            identity(before)
            found = next((i for i, d in enumerate(records) if d["decision_id"] == before), None)
            if found is None:
                raise AnalysisHistoryError("analysis_history_changed")
            records = records[found + 1:]
        page = records[:limit]
        return {"items": page, "next_before": page[-1]["decision_id"] if len(records) > limit else None}

    def save(self, *, key, created_at, request, result):
        key = identity(key)
        doc = {"schema": SCHEMA, "decision_id": key,
               "created_at_utc": created_at.astimezone(timezone.utc).isoformat(),
               "request": request, "result": result}
        raw = json.dumps(doc, ensure_ascii=False, allow_nan=False, sort_keys=True).encode()
        if len(raw) > MAX_DOCUMENT:
            raise AnalysisHistoryError("analysis_history_too_large")
        decode(raw, key)
        root = self._checked()
        root.mkdir(parents=True, exist_ok=True)
        self._checked()
        with exclusive_file_lock(root / ".analysis_history.lock"):
            cleanup_temporary_files_durably(root, name_pattern=re.compile(r"\.analysis-[a-z0-9_]{8}\.tmp"),
                                            primary_error=None, synchronize_directory=fsync_directory)
            existing = self._raw(key)
            if existing is not None:
                if decode(existing, key) != decode(raw, key):
                    raise AnalysisHistoryError("analysis_history_conflict")
                fsync_directory(root)
                return
            # Fail visibly at the bounded catalogue limit; never prune old records.
            self.list_records(limit=1)
            if sum(1 for p in root.iterdir() if p.name.endswith(".json")) >= MAX_RECORDS:
                raise AnalysisHistoryError("analysis_history_scan_limit")
            if sum(p.stat().st_size for p in root.iterdir() if p.name.endswith(".json")) + len(raw) > MAX_TOTAL:
                raise AnalysisHistoryError("analysis_history_scan_limit")
            temporary = None
            try:
                with tempfile.NamedTemporaryFile(dir=root, prefix=".analysis-", suffix=".tmp", delete=False) as stream:
                    temporary = Path(stream.name)
                    stream.write(raw)
                    stream.flush()
                    os.fsync(stream.fileno())
                target = root / (key + ".json")
                if os.name == "nt":
                    os.rename(temporary, target)
                else:
                    os.link(temporary, target)
                fsync_directory(root)
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)
                    fsync_directory(root)
