import asyncio

from framework.schemas.session_state import SessionState, SessionStatus, SessionTimestamps
from framework.storage.session_store import SessionStore


def _make_state(session_id: str, goal_id: str, updated_at: str, status: SessionStatus) -> SessionState:
    return SessionState(
        session_id=session_id,
        goal_id=goal_id,
        status=status,
        timestamps=SessionTimestamps(
            started_at="2026-02-01T00:00:00",
            updated_at=updated_at,
            completed_at=None,
        ),
    )


def test_list_sessions_filters_and_orders(tmp_path):
    store = SessionStore(tmp_path)

    state_old = _make_state(
        "session_20260201_000001_abcd0001",
        "goal-1",
        "2026-02-01T00:00:10",
        SessionStatus.COMPLETED,
    )
    state_new = _make_state(
        "session_20260201_000002_abcd0002",
        "goal-2",
        "2026-02-01T00:01:00",
        SessionStatus.FAILED,
    )

    asyncio.run(store.write_state(state_old.session_id, state_old))
    asyncio.run(store.write_state(state_new.session_id, state_new))

    sessions = asyncio.run(store.list_sessions())
    assert [s.session_id for s in sessions] == [
        state_new.session_id,
        state_old.session_id,
    ]

    failed_sessions = asyncio.run(store.list_sessions(status="failed"))
    assert [s.session_id for s in failed_sessions] == [state_new.session_id]
