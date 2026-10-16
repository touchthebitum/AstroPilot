"""Run extracted UI code with the same timezone bootstrap as index.html."""
from functools import lru_cache
from pathlib import Path
import subprocess

from decision.timezone_authority import bundle_json


@lru_cache(maxsize=1)
def bootstrap():
    library = Path(__file__).resolve().parents[1] / "astropilot/web/timezone-authority.js"
    return "globalThis.NightMeritTimeData=" + bundle_json() + ";\n" + library.read_text(encoding="utf-8") + "\n"


def run_with_time_authority(command, **kwargs):
    """Feed Node via stdin, avoiding the Windows command-line size limit."""
    command = list(command)
    engine = Path(command[0]).stem.lower()
    if engine == "node":
        if command[1] == "-e":
            source = command[2]
        elif command[1] == "-":
            source = kwargs.pop("input")
        else:
            source = Path(command[1]).read_text(encoding="utf-8")
        kwargs["input"] = bootstrap() + source
        command = [command[0], "-"]
    else:
        # JavaScriptCore fallback used only by old local test environments.
        if "-e" in command:
            command[-1] = bootstrap() + command[-1]
        else:
            source = Path(command[-1]).read_text(encoding="utf-8")
            command = command[:-1] + ["-e", bootstrap() + source]
    kwargs.setdefault("encoding", "utf-8")
    return subprocess.run(command, **kwargs)
