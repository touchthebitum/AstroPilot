"""Portable inventory contract; real POSIX open/race tests run alongside this."""
from contextlib import nullcontext
from types import SimpleNamespace

import pytest

from astropilot.field_lab_store import FileFieldLabStore


def entry(name, *, regular=True, symlink=False):
    def is_file(*, follow_symlinks):
        assert follow_symlinks is False
        return regular

    def stat(*args, **kwargs):
        pytest.fail('unconditional per-name stat regresses NAS preflight')

    return SimpleNamespace(name=name, is_symlink=lambda: symlink,
                           is_file=is_file, stat=stat)


def scan(monkeypatch, entries, limit=3):
    monkeypatch.setattr('astropilot.field_lab_store.os.scandir',
                        lambda fd: nullcontext(iter(entries)))
    return list(FileFieldLabStore._names(123, limit))


def test_inventory_uses_nofollow_directory_types(monkeypatch):
    names = [f'{i:064x}.json' for i in range(3)]
    assert scan(monkeypatch, [entry(n) for n in names]) == names


@pytest.mark.parametrize('kind, error', [
    ('symlink', OSError), ('directory', ValueError), ('fifo', ValueError),
])
def test_inventory_still_refuses_nonregular_entries(monkeypatch, kind, error):
    with pytest.raises(error, match='regular_file_required'):
        scan(monkeypatch, [entry('a'*64+'.json', regular=False,
                                symlink=kind == 'symlink')])


def test_inventory_limit_and_names_still_fail_closed(monkeypatch):
    with pytest.raises(ValueError, match='name_limit_exceeded'):
        scan(monkeypatch, [entry(f'{i:064x}.json') for i in range(4)])
    with pytest.raises(ValueError, match='unexpected_artifact_file'):
        scan(monkeypatch, [entry('unexpected.json')])
