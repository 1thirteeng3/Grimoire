import pytest

from app.core.fsm import FSMState, InvalidTransitionError, SessionContext, StateManager


def test_valid_transition_path():
    manager = StateManager(SessionContext(session_id="sess_fsm_001"))
    manager.transition(FSMState.PERCEPTION_ROUTING)
    manager.transition(FSMState.RAG_RETRIEVAL)
    manager.transition(FSMState.INTERNAL_ITERATION)
    manager.transition(FSMState.OPERATOR_READY)
    manager.transition(FSMState.EXECUTION)
    manager.transition(FSMState.MEMORY_CONSOLIDATION)
    manager.transition(FSMState.IDLE)
    assert manager.ctx.state == FSMState.IDLE


def test_invalid_transition_raises():
    manager = StateManager(SessionContext(session_id="sess_fsm_002"))
    with pytest.raises(InvalidTransitionError):
        manager.transition(FSMState.EXECUTION)


def test_retry_circuit_breaker():
    manager = StateManager(SessionContext(session_id="sess_fsm_003", max_retries=2))
    assert manager.increment_retry() is True
    assert manager.increment_retry() is True
    assert manager.increment_retry() is False
    manager.reset_retries()
    assert manager.ctx.retries == 0
