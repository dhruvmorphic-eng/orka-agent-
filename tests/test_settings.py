import json
import os
import stat

import pytest

from orka.settings import load_credentials, save_credentials


def test_credentials_are_owner_only_and_env_wins(tmp_path, monkeypatch):
    path = tmp_path / 'data' / 'credentials.json'
    save_credentials('fake-test-key', 'claude-test', path)
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    monkeypatch.delenv('ANTHROPIC_MODEL', raising=False)
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'explicit-environment-key')
    load_credentials(path)
    assert os.environ['ANTHROPIC_API_KEY'] == 'explicit-environment-key'
    assert os.environ['ANTHROPIC_MODEL'] == 'claude-test'


def test_replace_and_invalid_file_do_not_leak_secret(tmp_path):
    path = tmp_path / 'credentials.json'
    save_credentials('old-fake-key', 'claude-test', path)
    save_credentials('new-fake-key', 'claude-test', path)
    assert json.loads(path.read_text())['ANTHROPIC_API_KEY'] == 'new-fake-key'
    assert list(tmp_path.iterdir()) == [path]
    path.write_text('malformed-secret-material')
    with pytest.raises(RuntimeError) as exc:
        load_credentials(path)
    assert 'malformed-secret-material' not in str(exc.value)


def test_dotenv_loads_without_interpolation_and_preserves_shell(tmp_path, monkeypatch):
    env = tmp_path / '.env'
    env.write_text('ANTHROPIC_API_KEY="fake-${SECRET}"\nANTHROPIC_MODEL=claude-file\nUNRELATED=ignored\n')
    monkeypatch.delenv('ANTHROPIC_API_KEY', raising=False)
    monkeypatch.setenv('ANTHROPIC_MODEL', 'claude-shell')
    monkeypatch.delenv('UNRELATED', raising=False)
    load_credentials(tmp_path / 'absent.json', env_path=env)
    assert os.environ['ANTHROPIC_API_KEY'] == 'fake-${SECRET}'
    assert os.environ['ANTHROPIC_MODEL'] == 'claude-shell'
    assert 'UNRELATED' not in os.environ
