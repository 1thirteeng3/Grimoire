from dataclasses import dataclass
from enum import Enum
from typing import Optional
from uuid import UUID


class FSMState(str, Enum):
    IDLE = "IDLE"
    PERCEPTION_ROUTING = "PERCEPTION_ROUTING"
    RAG_RETRIEVAL = "RAG_RETRIEVAL"
    INTERNAL_ITERATION = "INTERNAL_ITERATION"
    OPERATOR_READY = "OPERATOR_READY"
    PENDING_HUMAN_CONFLICT = "PENDING_HUMAN_CONFLICT"
    BROKEN_PACT = "BROKEN_PACT"
    EXECUTION = "EXECUTION"
    MEMORY_CONSOLIDATION = "MEMORY_CONSOLIDATION"
    PROMPT_BLOATING = "PROMPT_BLOATING"
    ERROR = "ERROR"


VALID_TRANSITIONS: dict[FSMState, set[FSMState]] = {
    FSMState.IDLE: {FSMState.PERCEPTION_ROUTING},
    FSMState.PERCEPTION_ROUTING: {FSMState.RAG_RETRIEVAL, FSMState.ERROR},
    FSMState.RAG_RETRIEVAL: {
        FSMState.INTERNAL_ITERATION,
        FSMState.PROMPT_BLOATING,
        FSMState.ERROR,
    },
    FSMState.INTERNAL_ITERATION: {
        FSMState.OPERATOR_READY,
        FSMState.PENDING_HUMAN_CONFLICT,
        FSMState.BROKEN_PACT,
    },
    FSMState.OPERATOR_READY: {FSMState.EXECUTION},
    FSMState.PENDING_HUMAN_CONFLICT: {
        FSMState.EXECUTION,
        FSMState.INTERNAL_ITERATION,
        FSMState.IDLE,
    },
    FSMState.BROKEN_PACT: {FSMState.EXECUTION, FSMState.IDLE},
    FSMState.EXECUTION: {FSMState.MEMORY_CONSOLIDATION, FSMState.ERROR},
    FSMState.MEMORY_CONSOLIDATION: {FSMState.IDLE},
    FSMState.PROMPT_BLOATING: {FSMState.IDLE},
    FSMState.ERROR: {FSMState.IDLE},
}


@dataclass
class SessionContext:
    session_id: str
    state: FSMState = FSMState.IDLE
    active_pact_id: Optional[UUID] = None
    retries: int = 0
    max_retries: int = 2


class InvalidTransitionError(Exception):
    pass


class StateManager:
    def __init__(self, context: SessionContext):
        self.ctx = context

    def transition(self, new_state: FSMState) -> None:
        allowed = VALID_TRANSITIONS.get(self.ctx.state, set())
        if new_state not in allowed:
            raise InvalidTransitionError(
                f"Transição inválida: {self.ctx.state} → {new_state}. "
                f"Permitidas: {sorted(s.value for s in allowed)}"
            )
        self.ctx.state = new_state

    def increment_retry(self) -> bool:
        self.ctx.retries += 1
        return self.ctx.retries <= self.ctx.max_retries

    def reset_retries(self) -> None:
        self.ctx.retries = 0
