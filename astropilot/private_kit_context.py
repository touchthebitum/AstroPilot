"""Display-only provenance supplied by the private Windows Sandbox launcher.

Never use these host paths for filesystem access, migration or subprocesses.
The application cannot inspect host storage from inside Sandbox.
"""
import json
from pathlib import PureWindowsPath
import re

ENVIRONMENT_KEY = "NIGHTMERIT_PRIVATE_COPY_CONTEXT"
SCHEMA = "nightmerit.private_copy_context.v1"
STABLE_SCHEMA = "nightmerit.private_copy_context.v2"
STABLE_GUEST_DATA = PureWindowsPath(r"C:\NightMeritData\profil")
GUEST_DATA = PureWindowsPath(r"C:\NightMeritResults\profil")


def private_kit_context(raw: str | None, *, build: str, data_directory: str):
    if raw is None:
        return {"status": "not_provided", "host": None}
    unavailable = {"status": "unavailable", "host": None}
    if not isinstance(raw, str) or len(raw) > 16384:
        return unavailable
    try:
        value = json.loads(raw)
        if not isinstance(value, dict) or value.get("schema") not in {SCHEMA, STABLE_SCHEMA}:
            return unavailable
        sha = value.get("source_sha")
        if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{40}", sha) or sha[:7] != build:
            return unavailable
        stable = value["schema"] == STABLE_SCHEMA
        guest = STABLE_GUEST_DATA if stable else GUEST_DATA
        keys = ("host_kit_directory", "host_results_directory", "guest_data_directory")
        if stable:
            keys += ("host_data_directory",)
        for key in keys:
            text = value.get(key)
            if (not isinstance(text, str) or not text or len(text) > 2048
                    or any(ord(c) < 32 or 0xD800 <= ord(c) <= 0xDFFF for c in text)
                    or ".." in PureWindowsPath(text).parts
                    or not PureWindowsPath(text).is_absolute()):
                return unavailable
        kit = PureWindowsPath(value["host_kit_directory"])
        results = PureWindowsPath(value["host_results_directory"])
        if results != kit / "RESULTATS" or PureWindowsPath(value["guest_data_directory"]) != guest:
            return unavailable
        if PureWindowsPath(data_directory) != guest:
            return unavailable
        host = {"kit_directory": str(kit), "data_directory": str(results / "profil")}
        if stable:
            host["data_directory"] = str(PureWindowsPath(value["host_data_directory"]))
            host["storage_mode"] = "stable_private_beta"
        return {"status": "provided_by_launcher", "host": host}
    except (ValueError, TypeError, UnicodeError):
        return unavailable
