"""Dispatch portable modes before initializing the web application."""
import sys


def main():
    if sys.argv[1:] == ["--demo-isolated-test-18841"]:
        from astropilot.demo_mode import main as demo_main
        demo_main(port=18841, open_browser=False)
        return 0
    if sys.argv[1:] == ["--demo-isolated-test-18837"]:
        from astropilot.demo_mode import main as demo_main
        demo_main(port=18837, open_browser=False)
        return 0
    if sys.argv[1:] == ["--demo-18831"]:
        from astropilot.demo_mode import main as demo_main
        demo_main()
        return 0
    if len(sys.argv) == 3 and sys.argv[1] == "--prepare-stable-beta":
        from astropilot.stable_beta_data import main as prepare_main
        prepare_main(sys.argv[2])
        return 0
    if sys.argv[1:] in (["--demo-data-transfer-18841"], ["--private-data-transfer-18841"], ["--private-data-transfer-18871"]):
        import os
        from pathlib import Path
        data_dir = os.environ.get("ASTROPILOT_DATA_DIR")
        if not data_dir or not Path(data_dir).is_absolute():
            raise SystemExit("An explicit absolute isolated profile is required.")
        from astropilot.profile_transfer_app import main as transfer_main
        transfer_main(port=int(sys.argv[1].rsplit("-", 1)[1]), open_browser=False,
                      demo=sys.argv[1:] == ["--demo-data-transfer-18841"])
        return 0
    if sys.argv[1:] == ["--demo-data-transfer-18831"]:
        import os
        from pathlib import Path
        data_dir = os.environ.get("ASTROPILOT_DATA_DIR")
        if not data_dir or not Path(data_dir).is_absolute():
            raise SystemExit("An explicit absolute demo profile is required.")
        from astropilot.profile_transfer_app import main as transfer_main
        transfer_main(port=18831, demo=True)
        return 0
    if sys.argv[1:] == ["--private-data-transfer-18831"]:
        import os
        from pathlib import Path

        data_dir = os.environ.get("ASTROPILOT_DATA_DIR")
        if not data_dir or not Path(data_dir).is_absolute():
            raise SystemExit("An explicit absolute ASTROPILOT_DATA_DIR is required for private tests.")
        from astropilot.profile_transfer_app import main as transfer_main
        transfer_main(port=18831, open_browser=False)
        return 0
    if sys.argv[1:] == ["--data-transfer"]:
        from astropilot.profile_transfer_app import main as transfer_main
        transfer_main()
        return 0
    if len(sys.argv) == 3 and sys.argv[1] == "--validate-data-backup":
        from astropilot.profile_backup import validate_profile_child
        validate_profile_child(sys.argv[2])
        return 0
    if sys.argv[1:2] == ["--guardian-http-worker"]:
        from astropilot.guardian_http_worker import main as worker_main
        return worker_main(sys.argv[2:])
    if sys.argv[1:2] == ["--guardian"]:
        from astropilot.guardian_host import main as guardian_main
        return guardian_main(sys.argv[2:])
    if sys.argv[1:] in (["--private-test-server-18831"], ["--private-test-server-18841"], ["--private-test-server-18871"]):
        # Opt-in isolated native-kit checks; never probe or reuse port 8000.
        import os
        from pathlib import Path

        data_dir = os.environ.get("ASTROPILOT_DATA_DIR")
        if not data_dir or not Path(data_dir).is_absolute():
            raise SystemExit("An explicit absolute ASTROPILOT_DATA_DIR is required for private tests.")
        Path(data_dir).mkdir(parents=True, exist_ok=True)
        import uvicorn
        from astropilot.app import app

        uvicorn.run(app, host="127.0.0.1", port=int(sys.argv[1].rsplit("-", 1)[1]))
        return 0
    from astropilot.launcher import main as launcher_main
    launcher_main()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
