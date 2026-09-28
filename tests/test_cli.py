from orka.cli import Terminal, clean
from orka.store import Store


def session(tmp_path):
    output = []
    terminal = Terminal(Store(tmp_path / 'cli.sqlite'), write=output.append, enabled=lambda: False)
    return terminal, output


def complete(t):
    for answer in ['Find SaaS buyers', 'Sales research software', 'SaaS founders', 'US',
                   'Explicit vendor requests', '20', '14', '5', 'web discussions']:
        t.handle(answer)


def test_conversation_approves_and_edits_revoke(tmp_path):
    t, output = session(tmp_path)
    complete(t)
    assert t.task['state'] == 'awaiting_approval'
    assert t.reviewed is not None
    t.handle('yes')
    assert t.task['approval'] is not None
    assert any('no research or emails have run' in line for line in output)
    t.handle('/edit geography UK')
    assert t.task['approval'] is None
    assert t.task['brief']['geography'] == 'UK'


def test_early_yes_cannot_approve(tmp_path):
    t, _ = session(tmp_path)
    t.handle('Find buyers')
    t.handle('yes')
    assert t.task['approval'] is None and t.task['brief']['offering'] == ''


def test_resume_and_stale_approval(tmp_path):
    t, _ = session(tmp_path)
    complete(t)
    other = Terminal(t.store, write=lambda _: None, enabled=lambda: False)
    other.handle('/resume 1')
    assert other.task == t.task
    t.handle('/edit geography UK')
    import pytest
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        other.handle('yes')
    assert exc.value.status_code == 409
    assert t.store.get(t.task['id'])['approval'] is None


def test_terminal_control_codes_are_not_rendered():
    assert clean('\x1b[31mhello\x1b[0m\x07') == 'hello'
