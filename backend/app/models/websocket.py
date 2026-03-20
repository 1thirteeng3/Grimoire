from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field, TypeAdapter

from app.models.pacts import InquisitorReport


class StateRAGRetrievalPayload(BaseModel):
    documents_scanned: int
    collections: list[str]


class StreamTokenPayload(BaseModel):
    delta: str


class ConfidenceUpdatePayload(BaseModel):
    state: Literal["convergent", "partial", "conflict"]


class PactRequestPayload(BaseModel):
    pact_id: str
    human_summary: str
    operator_proposal_raw: str
    critic_report: list[InquisitorReport]


class ExecutionSuccessPayload(BaseModel):
    stdout: str
    exit_code: int


class PromptBloatingPayload(BaseModel):
    domain: str
    current_tokens: int
    limit: int


class StateRAGRetrievalEvent(BaseModel):
    type: Literal["STATE_RAG_RETRIEVAL"] = "STATE_RAG_RETRIEVAL"
    payload: StateRAGRetrievalPayload


class StreamTokenEvent(BaseModel):
    type: Literal["STREAM_TOKEN"] = "STREAM_TOKEN"
    payload: StreamTokenPayload


class ConfidenceUpdateEvent(BaseModel):
    type: Literal["CONFIDENCE_UPDATE"] = "CONFIDENCE_UPDATE"
    payload: ConfidenceUpdatePayload


class PactRequestEvent(BaseModel):
    type: Literal["PACT_REQUEST"] = "PACT_REQUEST"
    payload: PactRequestPayload


class ExecutionSuccessEvent(BaseModel):
    type: Literal["EXECUTION_SUCCESS"] = "EXECUTION_SUCCESS"
    payload: ExecutionSuccessPayload


class PromptBloatingEvent(BaseModel):
    type: Literal["PROMPT_BLOATING"] = "PROMPT_BLOATING"
    payload: PromptBloatingPayload


class PongEvent(BaseModel):
    type: Literal["PONG"] = "PONG"


ServerEvent = Annotated[
    Union[
        StateRAGRetrievalEvent,
        StreamTokenEvent,
        ConfidenceUpdateEvent,
        PactRequestEvent,
        ExecutionSuccessEvent,
        PromptBloatingEvent,
        PongEvent,
    ],
    Field(discriminator="type"),
]

# Exportable adapter for parsing/validation where needed.
ServerEventAdapter = TypeAdapter(ServerEvent)
