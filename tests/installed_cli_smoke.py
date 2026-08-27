import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile


def main() -> None:
    executable = shutil.which("astropilot")

    if executable is None:
        raise RuntimeError("installed astropilot command was not found")

    with tempfile.TemporaryDirectory() as raw_data_dir:
        data_dir = Path(raw_data_dir)
        profile_path = data_dir / "user_profile.json"
        filters_path = data_dir / "user_filters.json"

        profile_path.write_text(
            json.dumps(
                {
                    "active_equipment": "samyang_183",
                    "available_equipment": ["samyang_183"],
                    "preferences": {},
                    "projects": {},
                    "sessions": [],
                }
            ),
            encoding="utf-8",
        )
        filters_path.write_text(
            json.dumps(
                {
                    "filters": [
                        {
                            "name": "Smoke Ha",
                            "type": "Ha",
                            "bandwidth_nm": 6.5,
                        },
                        {
                            "name": "Smoke OIII",
                            "type": "OIII",
                            "bandwidth_nm": 6.5,
                        },
                        {
                            "name": "Smoke SII",
                            "type": "SII",
                            "bandwidth_nm": 6.5,
                        },
                    ]
                }
            ),
            encoding="utf-8",
        )

        profile_before = profile_path.read_bytes()
        filters_before = filters_path.read_bytes()
        environment = os.environ.copy()
        environment["ASTROPILOT_DATA_DIR"] = str(data_dir)

        result = subprocess.run(
            [executable, "--target-object", "IC1396"],
            cwd=data_dir,
            env=environment,
            check=True,
            capture_output=True,
            text=True,
        )

        assert "Filtres conseillés : Smoke Ha" in result.stdout
        assert "Temps conseillé Smoke Ha : 9.0 h" in result.stdout
        assert profile_path.read_bytes() == profile_before
        assert filters_path.read_bytes() == filters_before


if __name__ == "__main__":
    main()
