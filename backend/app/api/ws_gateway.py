import json
import os
import logging
from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.config import settings
from app.core.fsm import FSMState, SessionContext, StateManager
from app.integrations.obsidian_cli import ObsidianCliError, read_note
from app.llm.deepseek_client import LLMConfigurationError, LLMProviderError, stream_operator_response
from app.models.pacts import InquisitorReport, StatelessPactModel, ToolCallIntent
from app.models.websocket import (
    ConfidenceUpdateEvent,
    ConfidenceUpdatePayload,
    PactRequestEvent,
    PactRequestPayload,
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
from app.persistence.sqlite_layer import (
    fetch_pact,
    record_pact_audit_event,
    save_pact,
    update_pact_status,
)
from app.rag.pipeline import build_rag_context
from app.rag.shadowing import has_dangerous_command

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


def _secret_key() -> bytes:
    return os.getenv("GRIMOIRE_PACT_HMAC_SECRET", "dev-insecure-secret").encode()


def _normalize_session_id(session_id: str) -> str:
    if len(session_id) >= 10:
        return session_id
    return f"{session_id}_grimoire"


def _build_risk_reports(query: str, shadowed_count: int) -> list[InquisitorReport]:
    reports: list[InquisitorReport] = []
    if shadowed_count > 0:
        reports.append(
            InquisitorReport(
                severity="WARN",
                technical_reasoning=(
                    f"Risco detectado: {shadowed_count} chunk(s) shadowed por conflito com dogmas."
                ),
            )
        )
    if has_dangerous_command(query):
        reports.append(
            InquisitorReport(
                severity="FATAL",
                technical_reasoning="Query contém padrão potencialmente destrutivo.",
            )
        )
    return reports


def _risk_human_summary(reports: list[InquisitorReport]) -> str:
    if not reports:
        return "Sem risco detectado."
    fatal = sum(1 for r in reports if r.severity == "FATAL")
    warn = sum(1 for r in reports if r.severity == "WARN")
    return (
        f"Ação requer aprovação humana. Relatório de risco: {fatal} FATAL, {warn} WARN. "
        "Revise antes de executar."
    )


async def _execute_llm_stream(
    ws: WebSocket,
    manager: StateManager,
    query: str,
    constitution: str,
    chunks_xml: str,
    pact_id: str | None = None,
) -> None:
    tokens: list[str] = []
    try:
        async for delta in stream_operator_response(
            query=query,
            constitution=constitution,
            chunks_xml=chunks_xml,
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
        if pact_id:
            await record_pact_audit_event(
                pact_id,
                manager.ctx.session_id,
                "EXECUTION_FAILED",
                {"reason": "LLM_CONFIGURATION_ERROR", "detail": str(exc)},
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
        if pact_id:
            await record_pact_audit_event(
                pact_id,
                manager.ctx.session_id,
                "EXECUTION_FAILED",
                {"reason": "LLM_PROVIDER_ERROR", "detail": str(exc)},
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
        if pact_id:
            await record_pact_audit_event(
                pact_id,
                manager.ctx.session_id,
                "EXECUTION_FAILED",
                {"reason": "UNEXPECTED_ERROR", "detail": str(exc)},
            )
        manager.transition(FSMState.IDLE)
        return

    final_text = "".join(tokens).strip() or "[sem conteúdo retornado pelo modelo]"
    if pact_id:
        await record_pact_audit_event(
            pact_id,
            manager.ctx.session_id,
            "EXECUTION_SUCCEEDED",
            {"output_size": len(final_text)},
        )
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
    risk_reports = _build_risk_reports(query=query, shadowed_count=rag_ctx.shadowed_count)
    force_human = bool(message.get("force_human_approval", False))
    if risk_reports or force_human:
        manager.transition(FSMState.PENDING_HUMAN_CONFLICT)
        session_id = _normalize_session_id(manager.ctx.session_id)
        tool_intent = ToolCallIntent(
            tool_name="llm_generate",
            literal_arguments={
                "query": query,
                "constitution": rag_ctx.constitution,
                "chunks_xml": rag_ctx.chunks_xml,
                "domains": [str(d) for d in domains],
            },
        )
        if force_human and not risk_reports:
            risk_reports = [
                InquisitorReport(
                    severity="INFO",
                    technical_reasoning="force_human_approval solicitado pelo cliente.",
                )
            ]
        pact = StatelessPactModel.create(
            session_id=session_id,
            entity_manifest_hash=f"shadowed:{rag_ctx.shadowed_count}",
            operator_proposal_raw=query,
            tool_intent=tool_intent,
            critic_report=risk_reports,
            secret_key=_secret_key(),
        )
        manager.ctx.active_pact_id = UUID(str(pact.pact_id))
        await save_pact(pact.model_dump_json(), str(pact.pact_id))
        await record_pact_audit_event(
            str(pact.pact_id),
            session_id,
            "PACT_CREATED",
            {
                "shadowed_count": rag_ctx.shadowed_count,
                "risk_count": len(risk_reports),
                "forced": force_human,
            },
        )
        await send_event(
            ws,
            PactRequestEvent(
                payload=PactRequestPayload(
                    pact_id=str(pact.pact_id),
                    human_summary=_risk_human_summary(risk_reports),
                    operator_proposal_raw=query,
                    critic_report=risk_reports,
                )
            ),
        )
        await record_pact_audit_event(
            str(pact.pact_id),
            session_id,
            "PACT_REQUEST_EMITTED",
            {"human_summary": _risk_human_summary(risk_reports)},
        )
        return

    await send_event(
        ws,
        ConfidenceUpdateEvent(payload=ConfidenceUpdatePayload(state="partial")),
    )
    manager.transition(FSMState.OPERATOR_READY)
    await send_event(ws, StreamTokenEvent(payload=StreamTokenPayload(delta="Contexto compilado. Iniciando LLM...")))
    manager.transition(FSMState.EXECUTION)
    await _execute_llm_stream(
        ws=ws,
        manager=manager,
        query=query,
        constitution=rag_ctx.constitution,
        chunks_xml=rag_ctx.chunks_xml,
    )


async def handle_pact_resolve(ws: WebSocket, manager: StateManager, message: dict) -> None:
    pact_id = str(message.get("pact_id", "")).strip()
    action = str(message.get("action", "APPROVE_AS_IS")).strip()
    modified_arguments = message.get("modified_arguments", {})
    if not pact_id:
        await send_event(
            ws,
            StreamTokenEvent(payload=StreamTokenPayload(delta="PACT_RESOLVE sem pact_id.")),
        )
        return
    if action not in {"APPROVE_AS_IS", "MODIFY_AND_APPROVE", "ABORT"}:
        await send_event(
            ws,
            StreamTokenEvent(payload=StreamTokenPayload(delta=f"Ação de pacto inválida: {action}")),
        )
        return

    row = await fetch_pact(pact_id)
    if row is None:
        await send_event(
            ws,
            StreamTokenEvent(payload=StreamTokenPayload(delta=f"Pacto não encontrado: {pact_id}")),
        )
        return

    pact_payload = {
        "pact_id": UUID(str(row["pact_id"])),
        "session_id": row["session_id"],
        "entity_manifest_hash": row["entity_manifest_hash"],
        "fsm_status": row["fsm_status"],
        "operator_proposal_raw": row["operator_proposal_raw"],
        "tool_intent": json.loads(row["tool_intent_json"]),
        "critic_report": json.loads(row["critic_report_json"]),
        "created_at": datetime.fromisoformat(row["created_at"]),
        "ttl_timestamp": datetime.fromisoformat(row["ttl_timestamp"]),
        "cryptographic_signature": row["cryptographic_signature"],
    }
    pact = StatelessPactModel.model_validate(pact_payload)
    if pact.is_expired():
        await update_pact_status(pact_id, "ABORTED")
        await record_pact_audit_event(
            pact_id,
            pact.session_id,
            "PACT_EXPIRED",
            {"action_attempted": action},
        )
        if manager.ctx.state == FSMState.PENDING_HUMAN_CONFLICT:
            manager.transition(FSMState.IDLE)
        await send_event(
            ws,
            StreamTokenEvent(payload=StreamTokenPayload(delta=f"Pacto expirado: {pact_id}")),
        )
        return

    if not pact.verify_signature(_secret_key()):
        await update_pact_status(pact_id, "ABORTED")
        await record_pact_audit_event(
            pact_id,
            pact.session_id,
            "PACT_SIGNATURE_INVALID",
            {"action_attempted": action},
        )
        if manager.ctx.state == FSMState.PENDING_HUMAN_CONFLICT:
            manager.transition(FSMState.IDLE)
        await send_event(
            ws,
            StreamTokenEvent(payload=StreamTokenPayload(delta=f"Assinatura inválida para pacto: {pact_id}")),
        )
        return

    if action == "ABORT":
        await update_pact_status(pact_id, "ABORTED")
        await record_pact_audit_event(
            pact_id,
            pact.session_id,
            "PACT_ABORTED_BY_HUMAN",
            {},
        )
        if manager.ctx.state == FSMState.PENDING_HUMAN_CONFLICT:
            manager.transition(FSMState.IDLE)
        await send_event(
            ws,
            StreamTokenEvent(payload=StreamTokenPayload(delta=f"Pacto abortado por decisão humana: {pact_id}")),
        )
        return

    literal_arguments = dict(pact.tool_intent.literal_arguments)
    if action == "MODIFY_AND_APPROVE":
        if not isinstance(modified_arguments, dict):
            await send_event(
                ws,
                StreamTokenEvent(payload=StreamTokenPayload(delta="modified_arguments inválido; esperado objeto.")),
            )
            return
        literal_arguments.update(modified_arguments)
        await update_pact_status(pact_id, "FORCED")
        await record_pact_audit_event(
            pact_id,
            pact.session_id,
            "PACT_FORCED_BY_HUMAN",
            {"modified_keys": sorted(modified_arguments.keys())},
        )
    else:
        await update_pact_status(pact_id, "APPROVED")
        await record_pact_audit_event(
            pact_id,
            pact.session_id,
            "PACT_APPROVED_BY_HUMAN",
            {},
        )

    query = str(literal_arguments.get("query", pact.operator_proposal_raw))
    constitution = str(literal_arguments.get("constitution", ""))
    chunks_xml = str(literal_arguments.get("chunks_xml", ""))

    if manager.ctx.state != FSMState.PENDING_HUMAN_CONFLICT:
        manager.ctx.state = FSMState.PENDING_HUMAN_CONFLICT
    manager.transition(FSMState.EXECUTION)
    await record_pact_audit_event(
        pact_id,
        pact.session_id,
        "EXECUTION_STARTED",
        {"tool_name": pact.tool_intent.tool_name},
    )
    await send_event(
        ws,
        StreamTokenEvent(payload=StreamTokenPayload(delta=f"Pacto aprovado. Executando: {pact_id}")),
    )
    await _execute_llm_stream(
        ws=ws,
        manager=manager,
        query=query,
        constitution=constitution,
        chunks_xml=chunks_xml,
        pact_id=pact_id,
    )
