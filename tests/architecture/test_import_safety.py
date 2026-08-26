from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tokenize


def test_all_tracked_python_files_compile():
    repository = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        ["git", "ls-files", "--", "*.py"],
        cwd=repository,
        capture_output=True,
        text=True,
        check=True,
    )

    python_files = [
        repository / relative_path
        for relative_path in result.stdout.splitlines()
    ]

    assert python_files

    for python_file in python_files:
        with tokenize.open(python_file) as source_file:
            source = source_file.read()

        compile(
            source,
            str(python_file),
            "exec",
            dont_inherit=True,
        )


def test_astro_score_is_safe_to_import():
    repository = Path(__file__).resolve().parents[2]
    environment = os.environ.copy()
    environment.update(
        {
            "ASTROPY_USE_SYSTEM_IERS": "1",
            "PYTHONNOUSERSITE": "1",
        }
    )

    import_script = """
import socket

def deny_connection(*args, **kwargs):
    raise AssertionError("Live network access is forbidden in tests")

socket.socket.connect = deny_connection
socket.create_connection = deny_connection

import astro_score
"""

    result = subprocess.run(
        [sys.executable, "-c", import_script],
        cwd=repository,
        env=environment,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
