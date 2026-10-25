"""Dispatch portable modes before initializing the web application."""
import sys


def main():
    if len(sys.argv) == 3 and sys.argv[1] == "--prepare-stable-beta":
        from astropilot.stable_beta_data import main as prepare_main
        prepare_main(sys.argv[2])
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
    from astropilot.launcher import main as launcher_main
    launcher_main()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
