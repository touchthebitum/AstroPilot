"""Release provenance checks use disposable Git repositories and no signing tools."""
import importlib.util
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]


def release_module():
    spec = importlib.util.spec_from_file_location(
        'release_source_identity', ROOT / 'scripts/release_macos.py')
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(ROOT / 'scripts'))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)
    return module


def git(root, *args):
    return subprocess.run(['git', *args], cwd=root, check=True,
                          capture_output=True, text=True)


@pytest.fixture
def repository(tmp_path):
    git(tmp_path, 'init')
    (tmp_path / 'source.py').write_text('original\n', encoding='utf-8')
    (tmp_path / '.gitignore').write_text('dist/\nbuild/\n', encoding='utf-8')
    git(tmp_path, 'add', '.')
    git(tmp_path, '-c', 'user.name=Qualification', '-c',
        'user.email=qualification@example.invalid', 'commit', '-m', 'Public fixture')
    # Existing exports must survive a refusal before any build/cleanup.
    output = tmp_path / 'dist/previous.zip'
    output.parent.mkdir()
    output.write_bytes(b'previous isolated candidate')
    return tmp_path


@pytest.mark.parametrize('change', ['tracked', 'staged', 'untracked', 'nested_untracked'])
def test_release_refuses_dirty_source_before_build(repository, change):
    release = release_module()
    if change in ('tracked', 'staged'):
        (repository / 'source.py').write_text('changed\n', encoding='utf-8')
        if change == 'staged':
            git(repository, 'add', 'source.py')
    else:
        path = repository / ('extra/package.py' if change == 'nested_untracked' else 'extra.py')
        path.parent.mkdir(exist_ok=True)
        path.write_text('untracked source\n', encoding='utf-8')
    calls = []

    def runner(command, **kwargs):
        calls.append(command)
        assert command[0] == 'git', 'No signing, submission or packaging command allowed'
        return subprocess.run(command, **kwargs)

    with pytest.raises(RuntimeError, match='clean committed checkout'):
        release.release(root=repository, codesign_identity='SIMULATED IDENTITY',
                        notary_profile='SIMULATED PROFILE', runner=runner,
                        build_function=lambda **kwargs: pytest.fail('Dirty source reached build'))
    assert (repository / 'dist/previous.zip').read_bytes() == b'previous isolated candidate'
    assert all(command[0] == 'git' for command in calls)


def test_clean_checkout_accepts_ignored_packaging_outputs(repository):
    release = release_module()
    built = []

    class BuildReached(Exception):
        pass

    def build(**kwargs):
        built.append(kwargs)
        raise BuildReached()

    def runner(command, **kwargs):
        assert command[0] == 'git'
        return subprocess.run(command, **kwargs)

    with pytest.raises(BuildReached):
        release.release(root=repository, codesign_identity='SIMULATED IDENTITY',
                        notary_profile='SIMULATED PROFILE', runner=runner,
                        build_function=build)
    assert len(built) == 1


@pytest.mark.parametrize('change', ['tracked', 'untracked', 'new_commit'])
def test_source_change_during_build_prevents_verification_and_submission(repository, change):
    release = release_module()
    calls = []

    def build(**kwargs):
        (repository / ('extra.py' if change == 'untracked' else 'source.py')).write_text(
            'changed during build\n', encoding='utf-8')
        if change == 'new_commit':
            git(repository, 'add', 'source.py')
            git(repository, '-c', 'user.name=Qualification', '-c',
                'user.email=qualification@example.invalid', 'commit', '-m', 'Different source')
        application = repository / 'dist/AstroPilot.app'
        application.mkdir()
        return application

    def runner(command, **kwargs):
        calls.append(command)
        assert command[0] == 'git', 'No signing or submission command allowed'
        return subprocess.run(command, **kwargs)

    message = 'commit changed' if change == 'new_commit' else 'clean committed checkout'
    with pytest.raises(RuntimeError, match=message):
        release.release(root=repository, codesign_identity='SIMULATED IDENTITY',
                        notary_profile='SIMULATED PROFILE', runner=runner,
                        build_function=build)
    assert all(command[0] == 'git' for command in calls)


@pytest.mark.parametrize('revision', ['', 'a5c77a7', 'g' * 40])
def test_release_refuses_invalid_full_commit_before_build(tmp_path, revision):
    release = release_module()
    with pytest.raises(RuntimeError, match='checkout commit'):
        release.release(root=tmp_path, codesign_identity='SIMULATED IDENTITY',
                        notary_profile='SIMULATED PROFILE',
                        runner=lambda *a, **kw: type('Result', (), {'stdout': revision})(),
                        build_function=lambda **kw: pytest.fail('Invalid identity reached build'))


def test_git_failure_prevents_build(repository):
    release = release_module()

    def runner(command, **kwargs):
        raise subprocess.CalledProcessError(1, command)

    with pytest.raises(subprocess.CalledProcessError):
        release.release(root=repository, codesign_identity='SIMULATED IDENTITY',
                        notary_profile='SIMULATED PROFILE', runner=runner,
                        build_function=lambda **kw: pytest.fail('Unverifiable source reached build'))
