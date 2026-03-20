import json
import logging
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.config import settings
from app.core.fsm import FSMState, SessionContext, StateManager
from app.integrations.obsidian_cli import ObsidianCliError, read_note
from app.llm.deepseek_client import LLMConfigurationError, LLMProviderError, stream_operator_response
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


def _collect_chunks(message: dict[str, Any]) -> list[dict[str, str]]:
    raw_chunks = message.get("chunks", [])
    chunks: list[dict[str, str]] = []
    if isinstance(raw_chunks, list):
        for chunk in raw_chunks:
            if not isinstance(chunk, dict):
                continue
            text = chunk.get("text")
            if not isinstance(text, str) or not text.strip():
                continue
            chunks.append(
                {
                    "text": text,
                    "source": str(chunk.get("source", "unknown")),
                    "memory_type": str(chunk.get("memory_type", "vector_rag")),
                }
            )

    note_paths = message.get("obsidian_note_paths", [])
    if isinstance(note_paths, list):
        for note_path in note_paths:
            if not isinstance(note_path, str) or not note_path.strip():
                continue
            try:
                note_content = read_note(note_path)
            except ObsidianCliError as exc:
                logger.warning("Falha ao ler nota Obsidian '%s': %s", note_path, exc)
                continue
            chunks.append(
                {
                    "text": note_content[: settings.obsidian_note_max_chars],
                    "source": f"obsidian:{note_path}",
                    "memory_type": "obsidian_vault",
                }
            )
    return chunks


async def handle_intent(ws: WebSocket, manager: StateManager, message: dict) -> None:
    query = str(message.get("query", ""))
    if not query.strip():
        await send_event(
            ws,
            StreamTokenEvent(payload=StreamTokenPayload(delta="INTENT_SUBMIT sem query textual.")),
        )
        return
    raw_chunks = _collect_chunks(message)
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
        ConfidenceUpdateEvent(payload=ConfidenceUpdatePayload(state="partial")),
    )
    manager.transition(FSMState.OPERATOR_READY)
    await send_event(ws, StreamTokenEvent(payload=StreamTokenPayload(delta="Contexto compilado. Iniciando LLM...")))
    manager.transition(FSMState.EXECUTION)

    tokens: list[str] = []
    try:
        async for delta in stream_operator_response(
            query=query,
            constitution=rag_ctx.constitution,
            chunks_xml=rag_ctx.chunks_xml,
        ):
            tokens.append(delta)
            await send_event(ws, StreamTokenEvent(payload=StreamTokenPayload(delta=delta)))
    except LLMConfigurationError as exc:
        manager.transition(FSMState.ERROR)
        await send_event(
            ws,
            ConfidenceUpdateEvent(payload=ConfidenceUpdatePayload(state="conflict")),
        )
        await send_event(
            ws,
            StreamTokenEvent(payload=StreamTokenPayload(delta=f"LLM não configurado: {exc}")),
        )
        manager.transition(FSMState.IDLE)
        return
    except LLMProviderError as exc:
        manager.transition(FSMState.ERROR)
        await send_event(
            ws,
            ConfidenceUpdateEvent(payload=ConfidenceUpdatePayload(state="conflict")),
        )
        await send_event(
            ws,
            StreamTokenEvent(payload=StreamTokenPayload(delta=f"Falha no provedor LLM: {exc}")),
        )
        manager.transition(FSMState.IDLE)
        return
    except Exception as exc:
        logger.exception("Erro inesperado no streaming LLM: %s", exc)
        manager.transition(FSMState.ERROR)
        await send_event(
            ws,
            ConfidenceUpdateEvent(payload=ConfidenceUpdatePayload(state="conflict")),
        )
        await send_event(
            ws,
            StreamTokenEvent(payload=StreamTokenPayload(delta="Erro inesperado no operador LLM.")),
        )
        manager.transition(FSMState.IDLE)
        return

    final_text = "".join(tokens).strip() or "[sem conteúdo retornado pelo modelo]"
    await send_event(
        ws,
        ConfidenceUpdateEvent(payload=ConfidenceUpdatePayload(state="convergent")),
    )
    await send_event(
        ws,
        ExecutionSuccessEvent(payload=ExecutionSuccessPayload(stdout=final_text, exit_code=0)),
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
