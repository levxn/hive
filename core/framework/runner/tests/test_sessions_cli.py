import asyncio
import json
from types import SimpleNamespace

from framework.graph.executor import ExecutionResult
from framework.runner.cli import cmd_resume, cmd_sessions_list
from framework.schemas.session_state import SessionState, SessionStatus, SessionTimestamps
from framework.storage.session_store import SessionStore


def _make_state(session_id: str, updated_at: str) -> SessionState:
    return SessionState(
        session_id=session_id,
        goal_id="goal-1",
        status=SessionStatus.FAILED,
        timestamps=SessionTimestamps(
            started_at="2026-02-01T00:00:00",
            updated_at=updated_at,
            completed_at=None,
        ),
        input_data={"foo": "bar"},
        memory={"memory_key": "memory_value"},
        checkpoint_enabled=True,
        latest_checkpoint_id="cp_test_checkpoint",
    )


def test_cmd_sessions_list_json(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("HOME", str(tmp_path))
    agent_path = tmp_path / "agent"
    agent_path.mkdir(parents=True, exist_ok=True)

    store = SessionStore(tmp_path / ".hive" / "agents" / agent_path.name)
    state = _make_state("session_20260201_000001_abcd0001", "2026-02-01T00:01:00")
    asyncio.run(store.write_state(state.session_id, state))

    args = SimpleNamespace(
        agent_path=str(agent_path),
        status="all",
        has_checkpoints=False,
        json=True,
    )
    rc = cmd_sessions_list(args)
    assert rc == 0

    out = capsys.readouterr().out.strip()
    payload = json.loads(out)
    assert payload[0]["session_id"] == state.session_id


def test_cmd_resume_builds_session_state(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("HOME", str(tmp_path))
    agent_path = tmp_path / "agent"
    agent_path.mkdir(parents=True, exist_ok=True)

    store = SessionStore(tmp_path / ".hive" / "agents" / agent_path.name)
    state = _make_state("session_20260201_000002_abcd0002", "2026-02-01T00:02:00")
    asyncio.run(store.write_state(state.session_id, state))

    captured = {}

    class FakeRunner:
        def run(self, input_data, session_state=None):
            captured["input"] = input_data
            captured["session_state"] = session_state
            return ExecutionResult(success=True, output={"ok": True})

        def cleanup(self):
            return None

    def fake_load(*_args, **_kwargs):
        return FakeRunner()

    monkeypatch.setattr("framework.runner.AgentRunner.load", fake_load)

    args = SimpleNamespace(
        agent_path=str(agent_path),
        session_id=state.session_id,
        checkpoint=None,
        input=None,
        input_file=None,
        tui=False,
        model=None,
    )
    rc = cmd_resume(args)
    assert rc == 0
    assert captured["input"] == {"foo": "bar"}
    assert captured["session_state"]["memory"] == {"memory_key": "memory_value"}
    assert captured["session_state"]["resume_from_checkpoint"] == "cp_test_checkpoint"

    _ = capsys.readouterr()
