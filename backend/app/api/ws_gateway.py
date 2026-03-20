import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.fsm import FSMState, SessionContext, StateManager
from app.models.websocket import (
    ConfidenceUpdateEvent,
    ConfidenceUpdatePayload,
    ExecutionSuccessEvent,
    ExecutionSuccessPayload,
    PromptBloatingEvent,
    PromptBloatingPayload,
    ServerEvent,
    StateRAGRetrievalEvent,
    StateRAGRetrievalPayload,
    StreamTokenEvent,
    StreamTokenPayload,
)
from app.rag.pipeline import build_rag_context

router = APIRouter()
logger = logging.getLogger("grimoire.ws")


@router.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    await websocket.accept()
    ctx = SessionContext(session_id=session_id)
    manager = StateManager(ctx)
    logger.info("WebSocket conectado: %s", session_id)
    try:
        while True:
            raw = await websocket.receive_text()
            message = json.loads(raw)
            msg_type = message.get("type")

            if msg_type == "INTENT_SUBMIT":
                await handle_intent(websocket, manager, message)
            elif msg_type == "PACT_RESOLVE":
                await handle_pact_resolve(websocket, manager, message)
            elif msg_type == "PING":
                await websocket.send_text(json.dumps({"type": "PONG"}))
            else:
                logger.warning("Tipo de mensagem desconhecido: %s", msg_type)
    except WebSocketDisconnect:
        logger.info("WebSocket desconectado: %s", session_id)


async def send_event(ws: WebSocket, event: ServerEvent) -> None:
    await ws.send_text(event.model_dump_json())


async def handle_intent(ws: WebSocket, manager: StateManager, message: dict) -> None:
    raw_chunks = message.get("chunks", [])
    if not isinstance(raw_chunks, list):
        raw_chunks = []
    query = str(message.get("query", ""))
    domains = message.get("domains", ["generic"])
    if not isinstance(domains, list) or not domains:
        domains = ["generic"]

    manager.transition(FSMState.PERCEPTION_ROUTING)
    manager.transition(FSMState.RAG_RETRIEVAL)
    await send_event(
        ws,
        StateRAGRetrievalEvent(
            payload=StateRAGRetrievalPayload(
                documents_scanned=len(raw_chunks),
                collections=sorted(
                    {
                        str(chunk.get("source", "unknown"))
                        for chunk in raw_chunks
                        if isinstance(chunk, dict)
                    }
                ),
            )
        ),
    )

    try:
        rag_ctx = build_rag_context(query=query, raw_chunks=raw_chunks, domains=[str(d) for d in domains])
    except Exception as exc:
        logger.exception("Falha no pipeline RAG para sessão %s: %s", manager.ctx.session_id, exc)
        manager.transition(FSMState.ERROR)
        await send_event(
            ws,
            StreamTokenEvent(payload=StreamTokenPayload(delta="Erro ao processar intenção. Estado movido para ERROR.")),
        )
        manager.transition(FSMState.IDLE)
        return

    if rag_ctx.prompt_bloat:
        manager.transition(FSMState.PROMPT_BLOATING)
        await send_event(
            ws,
            PromptBloatingEvent(
                payload=PromptBloatingPayload(
                    domain=str(rag_ctx.prompt_bloat["domain"]),
                    current_tokens=int(rag_ctx.prompt_bloat["current_tokens"]),
                    limit=int(rag_ctx.prompt_bloat["limit"]),
                )
            ),
        )
        manager.transition(FSMState.IDLE)
        return

    manager.transition(FSMState.INTERNAL_ITERATION)
    await send_event(
        ws,
        ConfidenceUpdateEvent(payload=ConfidenceUpdatePayload(state="convergent")),
    )
    manager.transition(FSMState.OPERATOR_READY)
    await send_event(
        ws,
        StreamTokenEvent(payload=StreamTokenPayload(delta=f"Contexto compilado ({rag_ctx.top_k} top chunks).")),
    )
    manager.transition(FSMState.EXECUTION)
    await send_event(
        ws,
        ExecutionSuccessEvent(payload=ExecutionSuccessPayload(stdout="Fase 0: execução simulada", exit_code=0)),
    )
    manager.transition(FSMState.MEMORY_CONSOLIDATION)
    manager.transition(FSMState.IDLE)


async def handle_pact_resolve(ws: WebSocket, manager: StateManager, message: dict) -> None:
    pact_id = str(message.get("pact_id", "unknown"))
    action = str(message.get("action", "UNKNOWN"))
    await send_event(
        ws,
        StreamTokenEvent(
            payload=StreamTokenPayload(delta=f"PACT_RESOLVE recebido: pact_id={pact_id} action={action}")
        ),
    )
    if manager.ctx.state == FSMState.PENDING_HUMAN_CONFLICT:
        manager.transition(FSMState.IDLE)
