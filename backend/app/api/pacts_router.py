import json
import os
from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.models.pacts import StatelessPactModel, ToolCallIntent
from app.persistence.sqlite_layer import fetch_pact, record_pact_audit_event, update_pact_status

router = APIRouter(tags=["pacts"])


class PactResolveRequest(BaseModel):
    action: Literal["APPROVE_AS_IS", "MODIFY_AND_APPROVE", "ABORT"]
    modified_arguments: dict = Field(default_factory=dict)


def _secret_key() -> bytes:
    return os.getenv("GRIMOIRE_PACT_HMAC_SECRET", "dev-insecure-secret").encode()


@router.post("/pacts/{pact_id}/resolve")
async def resolve_pact(pact_id: str, payload: PactResolveRequest):
    row = await fetch_pact(pact_id)
    if row is None:
        return JSONResponse(status_code=404, content={"error_code": "PACT_NOT_FOUND"})

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
        await record_pact_audit_event(
            pact_id,
            pact.session_id,
            "PACT_EXPIRED",
            {"source": "REST", "action_attempted": payload.action},
        )
        return JSONResponse(
            status_code=410,
            content={
                "error_code": "PACT_EXPIRED",
                "message": "Pacto expirado e inelegível para execução.",
            },
        )

    if not pact.verify_signature(_secret_key()):
        await record_pact_audit_event(
            pact_id,
            pact.session_id,
            "PACT_SIGNATURE_INVALID",
            {"source": "REST", "action_attempted": payload.action},
        )
        return JSONResponse(
            status_code=403,
            content={"error_code": "PACT_SIGNATURE_INVALID", "message": "Assinatura inválida."},
        )

    if payload.action == "ABORT":
        await update_pact_status(pact_id, "ABORTED")
        await record_pact_audit_event(
            pact_id,
            pact.session_id,
            "PACT_ABORTED_BY_HUMAN",
            {"source": "REST"},
        )
        return {"status": "aborted", "pact_id": pact_id}

    if payload.action == "MODIFY_AND_APPROVE" and payload.modified_arguments:
        # Fase 0 apenas sinaliza modificação; execução literal entra na Fase 1.
        _ = ToolCallIntent(
            tool_name=pact.tool_intent.tool_name,
            literal_arguments=payload.modified_arguments,
        )

        await record_pact_audit_event(
            pact_id,
            pact.session_id,
            "PACT_FORCED_BY_HUMAN",
            {"source": "REST", "modified_keys": sorted(payload.modified_arguments.keys())},
        )

    await update_pact_status(pact_id, "APPROVED")
    if payload.action == "APPROVE_AS_IS":
        await record_pact_audit_event(
            pact_id,
            pact.session_id,
            "PACT_APPROVED_BY_HUMAN",
            {"source": "REST"},
        )
    return {
        "status": "approved",
        "pact_id": pact_id,
        "approved_at": datetime.now(timezone.utc).isoformat(),
    }
