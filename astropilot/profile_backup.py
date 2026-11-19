"""Offline, bounded, byte-preserving profile transfer. Never merges profiles.

Call only from the separate transfer process, with observing/Guardian writers
stopped. Hashes detect corruption; they do not authenticate an archive's author.
"""
from datetime import datetime, timezone
import hashlib
import errno
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import shutil
import struct
import subprocess
import sys
import tempfile
import zipfile
import zlib

from astropilot.field_lab_paths import require_user_directory
from astropilot.user_profile import validate_user_profile
from astropilot.durable_file_publication import fsync_directory


def canonical_version():
    from astropilot.app import canonical_version as version
    return version()

SCHEMA = "nightmerit.profile_backup.v1"
MAX_ARCHIVE = 64 * 1024 * 1024
MAX_TOTAL = 128 * 1024 * 1024
MAX_FILE = 8 * 1024 * 1024
MAX_FILES = 5000
MAX_MANIFEST = 2 * 1024 * 1024
ZIP_CHUNK = 64 * 1024
STORES = frozenset({"analysis_history", "decision_lineage", "execution_lineage", "decision_forecast_evidence",
                    "field_observations", "outcome_evaluations", "search_forecast_history"})
LOCAL_ONLY = frozenset({"Logs", "guardian", "guardian_scheduler", ".DS_Store",
                        ".outcome_history_cursor.key", ".outcome_history_cursor.key.lock"})


class BackupError(ValueError):
    pass


def profile_state(root):
    """Identify startup state without initializing or changing a user profile.

    Existing traces still block restoration. Never remove them to make a copy
    appear empty; guide the operator to a fresh kit instead.
    """
    root = _safe_root(root)
    entries = list(root.iterdir()) if root.exists() else []
    if not entries:
        return "empty"
    for path in entries:
        info = path.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise BackupError("backup_unsafe_path")
    if any(p.name == "user_profile.json" and p.is_file() for p in entries):
        return "profile"
    if all(p.name in LOCAL_ONLY or (p.name.startswith(".") and p.name.endswith(".lock"))
           for p in entries):
        return "runtime_only"
    marker = root / ".nightmerit-demo.json"
    if all(p.name == marker.name or p.name in LOCAL_ONLY or
           (p.name.startswith(".") and p.name.endswith(".lock")) for p in entries):
        info = marker.lstat() if marker.exists() else None
        if info and stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_size <= 256:
            try:
                with marker.open("rb") as stream:
                    raw = stream.read(257)
                if len(raw) <= 256 and _json(raw) == {"schema": "nightmerit.demo.v1"}:
                    return "demo_started"
            except (OSError, BackupError):
                pass
    return "unrecognized"


def _json(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise BackupError("backup_invalid")
            result[key] = value
        return result
    try:
        return json.loads(raw, object_pairs_hook=unique,
                          parse_constant=lambda _: (_ for _ in ()).throw(BackupError("backup_invalid")))
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise BackupError("backup_invalid") from exc


def _allowed(name):
    if not isinstance(name, str) or PurePosixPath(name).as_posix() != name:
        return False
    if name in {"user_profile.json", "user_filters.json", ".nightmerit-demo.json"}:
        return True
    parts = PurePosixPath(name).parts
    return (len(parts) == 2 and parts[0] in STORES
            and re.fullmatch(r"[A-Za-z0-9_-]{1,200}\.json", parts[1]) is not None
            and parts[1].split(".")[0].upper() not in
            {"CON", "PRN", "AUX", "NUL", *[f"COM{i}" for i in range(1, 10)], *[f"LPT{i}" for i in range(1, 10)]})


def _safe_root(root):
    root = Path(root).absolute()
    if ".." in root.parts or any(p.is_symlink() or (p.exists() and
            getattr(p.lstat(), "st_file_attributes", 0) & 0x400) for p in (root, *root.parents)):
        raise BackupError("backup_unsafe_path")
    try:
        require_user_directory(root)
    except ValueError as exc:
        raise BackupError("backup_unsafe_path") from exc
    if root.exists() and not root.is_dir():
        raise BackupError("backup_unsafe_path")
    return root


def _signature(info):
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def snapshot(root):
    """Read known domain documents only; unknown documents fail closed."""
    root = _safe_root(root)
    if not root.exists():
        return {}
    result = {}
    total = 0
    def scan(folder):
        nonlocal total
        for path in sorted(folder.iterdir()):
            info = path.lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                raise BackupError("backup_unsafe_path")
            if path.name in LOCAL_ONLY or (path.name.startswith(".") and path.name.endswith(".lock")):
                continue
            if stat.S_ISDIR(info.st_mode):
                if folder != root or path.name not in STORES:
                    raise BackupError("backup_unsupported_file")
                scan(path)
                continue
            name = path.relative_to(root).as_posix()
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or not _allowed(name):
                raise BackupError("backup_unsupported_file")
            total += info.st_size
            if info.st_size > MAX_FILE or total > MAX_TOTAL or len(result) >= MAX_FILES:
                raise BackupError("backup_too_large")
            flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_BINARY", 0)
            fd = os.open(path, flags)
            try:
                opened = os.fstat(fd)
                # Windows stat/fstat can expose different ctime semantics. Match
                # the opened identity/size/mtime, then check the path's full
                # signature (including ctime) again after reading.
                if not stat.S_ISREG(opened.st_mode) or _signature(info)[:4] != _signature(opened)[:4]:
                    raise BackupError("backup_changed")
                with os.fdopen(fd, "rb", closefd=False) as stream:
                    raw = stream.read(MAX_FILE + 1)
                if len(raw) > MAX_FILE or _signature(info) != _signature(path.lstat()):
                    raise BackupError("backup_changed")
            finally:
                os.close(fd)
            result[name] = raw
    scan(root)
    return result


def validate_documents(files):
    if "user_profile.json" not in files or len(files) > MAX_FILES:
        raise BackupError("backup_invalid")
    if sum(map(len, files.values())) > MAX_TOTAL:
        raise BackupError("backup_too_large")
    seen = set()
    for name, raw in files.items():
        if not _allowed(name) or name.casefold() in seen or len(raw) > MAX_FILE:
            raise BackupError("backup_invalid")
        seen.add(name.casefold())
        if not isinstance(_json(raw), dict):
            raise BackupError("backup_invalid")
    if ".nightmerit-demo.json" in files:
        if _json(files[".nightmerit-demo.json"]) != {"schema": "nightmerit.demo.v1"}:
            raise BackupError("backup_invalid")
    try:
        profile = validate_user_profile(_json(files["user_profile.json"]), Path("user_profile.json"))
    except Exception as exc:
        raise BackupError("backup_incompatible") from exc
    return {"projects": len(profile.get("projects", {})) + len(profile.get("archived_projects", {})),
            "observations": sum(n.startswith("field_observations/") for n in files),
            "sessions": sum(n.startswith("execution_lineage/") for n in files),
            "comparisons": sum(n.startswith("outcome_evaluations/") for n in files)}


def _write_files(folder, files):
    for name, raw in files.items():
        target = folder / name
        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        with target.open("xb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        target.chmod(0o600)


def validate_graph(files, *, review=False):
    """Use production read gates in a disposable child, never the active profile."""
    summary = validate_documents(files)
    with tempfile.TemporaryDirectory(prefix="nightmerit-backup-check-") as temporary:
        # Canonicalize only our freshly created temporary directory: macOS can
        # expose its temporary root through /var -> /private/var. The source
        # profile and archive paths still pass their unchanged safety checks.
        temporary_root = Path(temporary).resolve(strict=True)
        folder = temporary_root / "profile"
        folder.mkdir()
        _write_files(folder, files)
        report = temporary_root / "result.json"
        env = {k: v for k, v in os.environ.items() if not k.startswith(("ASTROPILOT_", "FIELD_LAB_", "NIGHTMERIT_"))}
        env["ASTROPILOT_DATA_DIR"] = str(folder)
        args = ([sys.executable] if getattr(sys, "frozen", False)
                else [sys.executable, "-m", "astropilot.portable_entry"])
        try:
            run = subprocess.run(args + ["--validate-data-backup", str(report)], env=env,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=90)
            result = _json(report.read_bytes())
            if run.returncode or not isinstance(result, dict) or result.get("validated") is not True:
                raise BackupError("backup_incompatible")
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise BackupError("backup_incompatible") from exc
    if review:
        if not isinstance(result.get('project_details'), list):
            raise BackupError('backup_incompatible')
        return {**summary, 'project_details': result['project_details']}
    return summary


def inspect_backup_for_review(raw):
    return inspect_backup(raw, validator=lambda files: validate_graph(files, review=True))


def create_backup(root, *, validator=validate_graph):
    files = snapshot(root)
    if not files:
        raise BackupError("backup_no_user_data")
    summary = validator(files)
    # Detect a writer changing, adding or removing any domain document.
    if snapshot(root) != files:
        raise BackupError("backup_changed")
    manifest = {"schema": SCHEMA, "application_version": canonical_version(),
                "created_at_utc": datetime.now(timezone.utc).isoformat(),
                "files": {n: {"size": len(v), "sha256": hashlib.sha256(v).hexdigest()}
                          for n, v in files.items()}}
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False))
        for name, raw in files.items():
            archive.writestr("data/" + name, raw)
    raw = stream.getvalue()
    if len(raw) > MAX_ARCHIVE:
        raise BackupError("backup_too_large")
    return raw, summary


def _central_directory(raw):
    """Bound the actual directory count before ZipFile allocates its entries.

    The backup producer never needs ZIP64 or multi-disk archives. Do not trust
    the EOCD entry count alone: ZipFile enumerates the directory's actual bytes.
    """
    end = raw.rfind(b"PK\x05\x06", max(0, len(raw) - 65557))
    if end < 0 or end + 22 > len(raw):
        raise BackupError("backup_invalid")
    _, disk, directory_disk, disk_count, count, size, offset, comment = struct.unpack_from("<4s4H2IH", raw, end)
    if (disk or directory_disk or disk_count != count or not 1 <= count <= MAX_FILES + 1
            or end + 22 + comment != len(raw) or offset + size != end):
        raise BackupError("backup_invalid")
    position, actual = offset, 0
    while position < end:
        if position + 46 > end or raw[position:position + 4] != b"PK\x01\x02":
            raise BackupError("backup_invalid")
        name, extra, annotation = struct.unpack_from("<3H", raw, position + 28)
        position += 46 + name + extra + annotation
        actual += 1
        if actual > MAX_FILES + 1 or position > end:
            raise BackupError("backup_invalid")
    if position != end or actual != count:
        raise BackupError("backup_invalid")
    return offset


def _read_member(raw, item, limit, directory_offset):
    """Decode the actual stream with bounded output, including its true EOF.

    ZipExtFile truncates output at the declared file_size. Its read(-1) can
    allocate a much larger deflate output before truncating it, hiding a forged
    length. Decode compressed blocks directly and reject any extra output.
    """
    header = struct.unpack_from("<4s5H3I2H", raw, item.header_offset)
    if (header[0] != b"PK\x03\x04" or header[2] != item.flag_bits
            or header[3] != item.compress_type):
        raise BackupError("backup_invalid")
    name_start = item.header_offset + 30
    start = name_start + header[9] + header[10]
    end = start + item.compress_size
    if (item.header_offset < 0 or end > directory_offset
            or raw[name_start:name_start + header[9]] != item.filename.encode("utf-8")
            or item.file_size > limit):
        raise BackupError("backup_invalid")
    if not item.flag_bits & 8 and header[6:9] != (item.CRC, item.compress_size, item.file_size):
        raise BackupError("backup_invalid")
    result = bytearray()
    decoder = zlib.decompressobj(-zlib.MAX_WBITS) if item.compress_type == zipfile.ZIP_DEFLATED else None
    for position in range(start, end, ZIP_CHUNK):
        block = memoryview(raw)[position:min(position + ZIP_CHUNK, end)]
        if decoder is None:
            result.extend(block)
            if len(result) > item.file_size or len(result) > limit:
                raise BackupError("backup_invalid")
            continue
        while block:
            decoded = decoder.decompress(block, min(ZIP_CHUNK, item.file_size - len(result) + 1))
            result.extend(decoded)
            if len(result) > item.file_size or len(result) > limit or decoder.unused_data:
                raise BackupError("backup_invalid")
            block = decoder.unconsumed_tail
    if (decoder is not None and not decoder.eof) or len(result) != item.file_size or zlib.crc32(result) != item.CRC:
        raise BackupError("backup_invalid")
    return bytes(result)


def inspect_backup(raw, *, validator=validate_graph):
    if len(raw) > MAX_ARCHIVE:
        raise BackupError("backup_too_large")
    try:
        directory_offset = _central_directory(raw)
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            entries = archive.infolist()
            names = [i.filename for i in entries]
            if (len(entries) > MAX_FILES + 1 or len(names) != len(set(names))
                    or "manifest.json" not in names or sum(i.file_size for i in entries) > MAX_TOTAL + MAX_MANIFEST):
                raise BackupError("backup_invalid")
            for item in entries:
                mode = item.external_attr >> 16
                if (item.flag_bits & 1 or stat.S_IFMT(mode) not in (0, stat.S_IFREG) or item.is_dir()
                        or item.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED)
                        or item.file_size > (MAX_MANIFEST if item.filename == "manifest.json" else MAX_FILE)):
                    raise BackupError("backup_invalid")
            manifest = _json(_read_member(raw, archive.getinfo("manifest.json"), MAX_MANIFEST, directory_offset))
            if (not isinstance(manifest, dict) or manifest.get("schema") != SCHEMA
                    or manifest.get("application_version") != canonical_version()
                    or not isinstance(manifest.get("files"), dict)):
                raise BackupError("backup_incompatible")
            if set(names) != {"manifest.json", *("data/" + n for n in manifest["files"])}:
                raise BackupError("backup_invalid")
            files = {}
            for name, record in manifest["files"].items():
                if not _allowed(name) or not isinstance(record, dict):
                    raise BackupError("backup_invalid")
                data = _read_member(raw, archive.getinfo("data/" + name), MAX_FILE, directory_offset)
                if (type(record.get("size")) is not int or len(data) != record["size"]
                        or hashlib.sha256(data).hexdigest() != record.get("sha256")):
                    raise BackupError("backup_invalid")
                files[name] = data
    except (zipfile.BadZipFile, KeyError, TypeError, RuntimeError, NotImplementedError, zlib.error, EOFError, struct.error) as exc:
        raise BackupError("backup_invalid") from exc
    summary = validator(files)
    return files, {**summary, "created_at_utc": manifest.get("created_at_utc"),
                   "application_version": manifest["application_version"]}


RESTORE_OWNER = "restore-owner.json"


def _restore_lock(root):
    from astropilot.file_lock import exclusive_file_lock
    root.parent.mkdir(parents=True, exist_ok=True)
    lock = root.parent / ".nightmerit-restoration.lock"
    if lock.exists() or lock.is_symlink():
        info = lock.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise BackupError("backup_unsafe_path")
    return exclusive_file_lock(lock)


def _mark_restore_stage(temporary, root, files):
    stage = temporary / "profile"
    info = stage.lstat()
    record = {"schema": "nightmerit.restore_stage.v1", "target": str(root),
              "directory": temporary.name, "device": info.st_dev, "inode": info.st_ino,
              "files": {name: len(raw) for name, raw in files.items()}}
    with (temporary / RESTORE_OWNER).open("x", encoding="utf-8") as stream:
        json.dump(record, stream)
        stream.flush()
        os.fsync(stream.fileno())
    fsync_directory(temporary)


def _cleanup_restore_stages_locked(root):
    # Do not fall back to unsafe path-based recursive deletion on other platforms.
    if not getattr(shutil.rmtree, "avoids_symlink_attacks", False):
        return []
    removed = []
    for temporary in root.parent.glob(".nightmerit-restore-*"):
        try:
            info = temporary.lstat()
            if not stat.S_ISDIR(info.st_mode):
                continue
            owner = temporary / RESTORE_OWNER
            owner_info = owner.lstat()
            if not stat.S_ISREG(owner_info.st_mode) or owner_info.st_nlink != 1 or owner_info.st_size > MAX_MANIFEST:
                continue
            record = _json(owner.read_bytes())
            if (record.get("schema") != "nightmerit.restore_stage.v1" or record.get("target") != str(root)
                    or record.get("directory") != temporary.name or not isinstance(record.get("files"), dict)):
                continue
            files = record["files"]
            if (not 1 <= len(files) <= MAX_FILES or any(not _allowed(n) or type(size) is not int
                    or not 0 <= size <= MAX_FILE for n, size in files.items())):
                continue
            entries = {p.name for p in temporary.iterdir()}
            if not entries <= {RESTORE_OWNER, "profile"}:
                continue
            stage = temporary / "profile"
            if "profile" in entries:
                stage_info = stage.lstat()
                if (not stat.S_ISDIR(stage_info.st_mode) or stage_info.st_dev != record.get("device")
                        or stage_info.st_ino != record.get("inode")):
                    continue
                valid = True
                for path in stage.iterdir():
                    path_info = path.lstat()
                    if stat.S_ISDIR(path_info.st_mode) and path.name in STORES:
                        children = list(path.iterdir())
                    else:
                        children = [path]
                    for child in children:
                        child_info = child.lstat()
                        name = child.relative_to(stage).as_posix()
                        if (not stat.S_ISREG(child_info.st_mode) or child_info.st_nlink != 1
                                or name not in files or child_info.st_size > files[name]):
                            valid = False
                            break
                    if not valid:
                        break
                if not valid:
                    continue
            # The common lock excludes every current restorer using this parent.
            # rmtree uses file descriptors and never follows a replaced symlink.
            shutil.rmtree(temporary)
            fsync_directory(root.parent)
            removed.append(temporary.name)
        except (OSError, BackupError, AttributeError, TypeError):
            # Unknown, unreadable or altered directories are preserved, never guessed.
            continue
    return removed


def cleanup_interrupted_restores(root):
    root = _safe_root(root)
    with _restore_lock(root):
        return _cleanup_restore_stages_locked(root)


def restore_empty(root, files, *, validator=validate_graph):
    root = _safe_root(root)
    with _restore_lock(root):
        _cleanup_restore_stages_locked(root)
        return _restore_empty_locked(root, files, validator=validator)


def _restore_empty_locked(root, files, *, validator=validate_graph):
    root = _safe_root(root)
    # Even unknown, hidden or unreadable data blocks replacement. No merge.
    if root.exists() and any(root.iterdir()):
        raise BackupError("backup_destination_not_empty")
    summary = validator(files)
    root.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".nightmerit-restore-", dir=root.parent) as temporary:
        stage = Path(temporary) / "profile"
        stage.mkdir(mode=0o700)
        _mark_restore_stage(Path(temporary), root, files)
        _write_files(stage, files)
        for directory in [p for p in stage.iterdir() if p.is_dir()] + [stage]:
            fsync_directory(directory)
        if snapshot(stage) != files:
            raise BackupError("backup_changed")
        _safe_root(root)
        had_empty_root = root.exists()
        if had_empty_root:
            if any(root.iterdir()):
                raise BackupError("backup_destination_not_empty")
            # rmdir checks emptiness atomically. Never move an old profile
            # into a temporary directory that cleanup could later remove.
            try:
                root.rmdir()
            except OSError as exc:
                if exc.errno in (errno.ENOTEMPTY, errno.EEXIST):
                    raise BackupError("backup_destination_not_empty") from exc
                raise
        try:
            # Directory publication: no per-file partially restored profile.
            os.rename(stage, root)
            fsync_directory(root.parent)
        except BaseException:
            if had_empty_root and not root.exists():
                root.mkdir(mode=0o700)
            raise
    return summary


def validate_profile_child(report):
    """Internal subprocess mode: existing API gates, no new decisions or credits."""
    from astropilot.app import create_app
    from astropilot.user_profile import load_user_profile
    profile = load_user_profile()
    from decision.filtering.filter_inventory_loader import FilterInventoryLoader
    FilterInventoryLoader.load()
    from astro_score import build_durable_tonight_application_service
    app = create_app(service_factory=build_durable_tonight_application_service,
                     guardian_renewal_enabled=False)
    routes = {r.path: r.endpoint for r in app.routes
              if hasattr(r, "endpoint") and "GET" in getattr(r, "methods", ())}
    from decision.services.intent_progress_credit import retained_projects
    project_details = []
    for project_id, project in retained_projects(profile).items():
        progress = routes["/v1/projects/{project_id}/progress"](project_id)
        filters = {item['acquisition_intent_id']: item['filter_type'] for item in progress['acquisition_intents']}
        targets = {item['acquisition_intent_id']: item['target_hours'] for item in progress['acquisition_intent_targets']}
        project_details.append({'project_id': project_id,
            'archived': project_id in profile.get('archived_projects', {}),
            'filters': [{'acquisition_intent_id': item['acquisition_intent_id'],
                         'filter_type': filters.get(item['acquisition_intent_id']),
                         'acquired_seconds': item['effective_total_seconds'],
                         'target_hours': targets.get(item['acquisition_intent_id'])}
                        for item in progress['intent_progress_breakdown']],
            'recorded_total_seconds': float(project.get('hours', 0)) * 3600})
    root = Path(os.environ["ASTROPILOT_DATA_DIR"])
    from astropilot.field_observation_store import FileFieldObservationStore
    FileFieldObservationStore(root / "field_observations").list_page(limit=1)
    for path in (root / "field_observations").glob("*.json"):
        routes["/v1/field-observations/{observation_id}"](path.stem)
    from astropilot.outcome_evaluation_store import FileOutcomeEvaluationStore
    for path in (root / "outcome_evaluations").glob("*.json"):
        FileOutcomeEvaluationStore(root / "outcome_evaluations")._load_path(path)
    for path in (root / "execution_lineage").glob("*.json"):
        routes["/v1/executions/{execution_id}/session"](path.stem)
    # Decode every stored lineage/evidence, including documents without credits.
    from astropilot.decision_acceptance_lineage_store import FileDecisionAcceptanceLineageStore
    from astropilot.execution_lineage_store import FileExecutionLineageStore
    from astropilot.decision_forecast_evidence_store import FileDecisionForecastEvidenceStore
    FileDecisionAcceptanceLineageStore(root / "decision_lineage").session_read_snapshot()
    for directory, store in [("decision_lineage", FileDecisionAcceptanceLineageStore),
                             ("execution_lineage", FileExecutionLineageStore)]:
        for path in (root / directory).glob("*.json"):
            store(root / directory)._load_path(path)
    for path in (root / "decision_forecast_evidence").glob("*.json"):
        FileDecisionForecastEvidenceStore(root / "decision_forecast_evidence").load(decision_id=path.stem)
    from astropilot.analysis_history import FileAnalysisHistory
    FileAnalysisHistory(root / "analysis_history").list_records(limit=1)
    from astropilot.search_forecast_history import FileSearchForecastHistory
    FileSearchForecastHistory(root / "search_forecast_history").list_records(limit=1)
    Path(report).write_text(json.dumps({"validated": True, "project_details": project_details}))
