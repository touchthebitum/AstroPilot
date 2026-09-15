import multiprocessing
import os
from pathlib import Path
from threading import Event, Thread

import pytest

import astropilot.file_lock as file_lock


def _hold_process_lock(lock_path: str, entered, release) -> None:
    with file_lock.exclusive_file_lock(Path(lock_path)):
        entered.set()
        release.wait(timeout=10)


def _wait_for_process_lock(lock_path: str, entered) -> None:
    with file_lock.exclusive_file_lock(Path(lock_path)):
        entered.set()


def test_two_threads_cannot_enter_same_lock_path_concurrently(tmp_path):
    lock_path = tmp_path / "shared.lock"
    equivalent_path = tmp_path / "unused" / ".." / "shared.lock"
    first_entered = Event()
    release_first = Event()
    second_entered = Event()

    def first():
        with file_lock.exclusive_file_lock(lock_path):
            first_entered.set()
            assert release_first.wait(timeout=5)

    def second():
        assert first_entered.wait(timeout=5)
        with file_lock.exclusive_file_lock(equivalent_path):
            second_entered.set()

    first_thread = Thread(target=first)
    second_thread = Thread(target=second)
    first_thread.start()
    second_thread.start()
    assert first_entered.wait(timeout=5)
    assert not second_entered.wait(timeout=0.1)

    release_first.set()
    first_thread.join(timeout=5)
    second_thread.join(timeout=5)

    assert not first_thread.is_alive()
    assert not second_thread.is_alive()
    assert second_entered.is_set()


def test_different_lock_paths_remain_independent(tmp_path):
    first_path = tmp_path / "first.lock"
    second_path = tmp_path / "second.lock"
    first_entered = Event()
    release_first = Event()
    second_entered = Event()

    def hold_first():
        with file_lock.exclusive_file_lock(first_path):
            first_entered.set()
            assert release_first.wait(timeout=5)

    thread = Thread(target=hold_first)
    thread.start()
    assert first_entered.wait(timeout=5)

    with file_lock.exclusive_file_lock(second_path):
        second_entered.set()

    assert second_entered.is_set()
    release_first.set()
    thread.join(timeout=5)
    assert not thread.is_alive()


@pytest.mark.skipif(os.name == "nt", reason="POSIX backend coverage")
def test_separate_processes_serialize_on_posix(tmp_path):
    context = multiprocessing.get_context("spawn")
    holder_entered = context.Event()
    release_holder = context.Event()
    contender_entered = context.Event()
    lock_path = tmp_path / "process.lock"
    holder = context.Process(
        target=_hold_process_lock,
        args=(str(lock_path), holder_entered, release_holder),
    )
    contender = context.Process(
        target=_wait_for_process_lock,
        args=(str(lock_path), contender_entered),
    )

    holder.start()
    assert holder_entered.wait(timeout=5)
    contender.start()
    assert not contender_entered.wait(timeout=0.2)

    release_holder.set()
    assert contender_entered.wait(timeout=5)
    holder.join(timeout=5)
    contender.join(timeout=5)

    assert holder.exitcode == 0
    assert contender.exitcode == 0


def test_lock_releases_after_normal_return(tmp_path):
    lock_path = tmp_path / "normal.lock"

    with file_lock.exclusive_file_lock(lock_path):
        pass

    with file_lock.exclusive_file_lock(lock_path):
        pass


def test_lock_releases_after_body_exception(tmp_path):
    lock_path = tmp_path / "exception.lock"

    with pytest.raises(RuntimeError, match="body failed"):
        with file_lock.exclusive_file_lock(lock_path):
            raise RuntimeError("body failed")

    with file_lock.exclusive_file_lock(lock_path):
        pass


def test_os_acquisition_failure_prevents_body_execution(tmp_path, monkeypatch):
    body_executed = False

    def fail_acquisition(handle):
        del handle
        raise OSError("lock unavailable")

    monkeypatch.setattr(file_lock, "_acquire_os_lock", fail_acquisition)

    with pytest.raises(OSError, match="lock unavailable"):
        with file_lock.exclusive_file_lock(tmp_path / "failure.lock"):
            body_executed = True

    assert body_executed is False


def test_unlock_failure_propagates(tmp_path, monkeypatch):
    monkeypatch.setattr(
        file_lock,
        "_release_os_lock",
        lambda handle: (_ for _ in ()).throw(OSError("unlock failed")),
    )

    with pytest.raises(OSError, match="unlock failed"):
        with file_lock.exclusive_file_lock(tmp_path / "unlock.lock"):
            pass


class _RecordingHandle:
    def __init__(self):
        self.positions = []

    def seek(self, position):
        self.positions.append(position)

    def fileno(self):
        return 42


class _RecordingMsvcrt:
    LK_LOCK = 1
    LK_UNLCK = 2

    def __init__(self):
        self.calls = []

    def locking(self, descriptor, mode, byte_count):
        self.calls.append((descriptor, mode, byte_count))


def test_fake_windows_backend_locks_and_unlocks_one_byte_at_offset_zero():
    """Adapter coverage only; this does not prove native Windows locking."""
    handle = _RecordingHandle()
    backend = _RecordingMsvcrt()

    file_lock._acquire_windows_lock(handle, backend)
    file_lock._release_windows_lock(handle, backend)

    assert handle.positions == [0, 0]
    assert backend.calls == [
        (42, backend.LK_LOCK, 1),
        (42, backend.LK_UNLCK, 1),
    ]


def test_fake_windows_acquisition_failure_never_yields(tmp_path, monkeypatch):
    """Adapter coverage only; this does not prove native Windows locking."""
    body_executed = False

    class FailingMsvcrt(_RecordingMsvcrt):
        def locking(self, descriptor, mode, byte_count):
            del descriptor, mode, byte_count
            raise OSError("windows lock unavailable")

    backend = FailingMsvcrt()
    monkeypatch.setattr(
        file_lock,
        "_acquire_os_lock",
        lambda handle: file_lock._acquire_windows_lock(handle, backend),
    )

    with pytest.raises(OSError, match="windows lock unavailable"):
        with file_lock.exclusive_file_lock(tmp_path / "windows-failure.lock"):
            body_executed = True

    assert body_executed is False
