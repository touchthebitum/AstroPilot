"""Dispatch portable modes before initializing the web application."""
import sys


def main():
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
