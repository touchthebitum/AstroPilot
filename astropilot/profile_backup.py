"""Offline, bounded, byte-preserving profile transfer. Never merges profiles.

Call only from the separate transfer process, with observing/Guardian writers
stopped. Hashes detect corruption; they do not authenticate an archive's author.
"""
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
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
STORES = frozenset({"decision_lineage", "execution_lineage", "decision_forecast_evidence",
                    "field_observations", "outcome_evaluations"})
LOCAL_ONLY = frozenset({"Logs", "guardian", "guardian_scheduler", ".DS_Store",
                        ".outcome_history_cursor.key", ".outcome_history_cursor.key.lock"})


class BackupError(ValueError):
    pass


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
    if name in {"user_profile.json", "user_filters.json"}:
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
                if not stat.S_ISREG(opened.st_mode) or _signature(info) != _signature(opened):
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
    try:
        profile = validate_user_profile(_json(files["user_profile.json"]), Path("user_profile.json"))
    except Exception as exc:
        raise BackupError("backup_incompatible") from exc
    return {"projects": len(profile.get("projects", {})),
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


def validate_graph(files):
    """Use production read gates in a disposable child, never the active profile."""
    summary = validate_documents(files)
    with tempfile.TemporaryDirectory(prefix="nightmerit-backup-check-") as temporary:
        folder = Path(temporary) / "profile"
        folder.mkdir()
        _write_files(folder, files)
        report = Path(temporary) / "result.json"
        env = {k: v for k, v in os.environ.items() if not k.startswith(("ASTROPILOT_", "FIELD_LAB_", "NIGHTMERIT_"))}
        env["ASTROPILOT_DATA_DIR"] = str(folder)
        args = ([sys.executable] if getattr(sys, "frozen", False)
                else [sys.executable, "-m", "astropilot.portable_entry"])
        try:
            run = subprocess.run(args + ["--validate-data-backup", str(report)], env=env,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=90)
            if run.returncode or _json(report.read_bytes()) != {"validated": True}:
                raise BackupError("backup_incompatible")
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise BackupError("backup_incompatible") from exc
    return summary


def create_backup(root, *, validator=validate_graph):
    files = snapshot(root)
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


def inspect_backup(raw, *, validator=validate_graph):
    if len(raw) > MAX_ARCHIVE:
        raise BackupError("backup_too_large")
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            entries = archive.infolist()
            names = [i.filename for i in entries]
            if (len(entries) > MAX_FILES + 1 or len(names) != len(set(names))
                    or "manifest.json" not in names or sum(i.file_size for i in entries) > MAX_TOTAL + 2 * 1024 * 1024):
                raise BackupError("backup_invalid")
            for item in entries:
                mode = item.external_attr >> 16
                if (item.flag_bits & 1 or stat.S_IFMT(mode) not in (0, stat.S_IFREG) or item.is_dir()
                        or item.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED)
                        or item.file_size > (2 * 1024 * 1024 if item.filename == "manifest.json" else MAX_FILE)):
                    raise BackupError("backup_invalid")
            manifest = _json(archive.read("manifest.json"))
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
                data = archive.read("data/" + name)
                if (type(record.get("size")) is not int or len(data) != record["size"]
                        or hashlib.sha256(data).hexdigest() != record.get("sha256")):
                    raise BackupError("backup_invalid")
                files[name] = data
    except (zipfile.BadZipFile, KeyError, TypeError, RuntimeError, NotImplementedError, zlib.error, EOFError) as exc:
        raise BackupError("backup_invalid") from exc
    summary = validator(files)
    return files, {**summary, "created_at_utc": manifest.get("created_at_utc"),
                   "application_version": manifest["application_version"]}


def restore_empty(root, files, *, validator=validate_graph):
    root = _safe_root(root)
    # Even unknown, hidden or unreadable data blocks replacement. No merge.
    if root.exists() and any(root.iterdir()):
        raise BackupError("backup_destination_not_empty")
    summary = validator(files)
    root.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".nightmerit-restore-", dir=root.parent) as temporary:
        stage = Path(temporary) / "profile"
        stage.mkdir(mode=0o700)
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
            os.rename(root, Path(temporary) / "empty")
        try:
            # Directory publication: no per-file partially restored profile.
            os.rename(stage, root)
            fsync_directory(root.parent)
        except BaseException:
            if had_empty_root and not root.exists():
                os.rename(Path(temporary) / "empty", root)
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
    for project_id in profile.get("projects", {}):
        routes["/v1/projects/{project_id}/progress"](project_id)
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
    Path(report).write_text(json.dumps({"validated": True}))
