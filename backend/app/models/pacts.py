import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from pydantic import UUID4, BaseModel, ConfigDict, Field

from app.config import settings


class InquisitorReport(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True)

    severity: Literal["INFO", "WARN", "FATAL"]
    violated_dogma_path: str | None = Field(default=None)
    shadowed_text: str | None = Field(default=None)
    technical_reasoning: str


class ToolCallIntent(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True)

    tool_name: str
    literal_arguments: dict[str, Any]


class StatelessPactModel(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    pact_id: UUID4
    session_id: str = Field(..., min_length=10)
    entity_manifest_hash: str
    fsm_status: Literal["PENDING_HUMAN_CONFLICT", "APPROVED", "FORCED", "ABORTED"]
    operator_proposal_raw: str
    tool_intent: ToolCallIntent
    critic_report: list[InquisitorReport]
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    ttl_timestamp: datetime
    cryptographic_signature: str

    @classmethod
    def create(
        cls,
        session_id: str,
        entity_manifest_hash: str,
        operator_proposal_raw: str,
        tool_intent: ToolCallIntent,
        critic_report: list[InquisitorReport],
        secret_key: bytes,
    ) -> "StatelessPactModel":
        from uuid import uuid4

        now = datetime.now(timezone.utc)
        ttl = now + timedelta(seconds=settings.pact_ttl_seconds)
        sign_payload = json.dumps(
            {
                "session_id": session_id,
                "tool_name": tool_intent.tool_name,
                "args": tool_intent.literal_arguments,
            },
            sort_keys=True,
        )
        sig = hmac.new(secret_key, sign_payload.encode(), hashlib.sha256).hexdigest()
        return cls(
            pact_id=uuid4(),
            session_id=session_id,
            entity_manifest_hash=entity_manifest_hash,
            fsm_status="PENDING_HUMAN_CONFLICT",
            operator_proposal_raw=operator_proposal_raw,
            tool_intent=tool_intent,
            critic_report=critic_report,
            created_at=now,
            ttl_timestamp=ttl,
            cryptographic_signature=f"sha256={sig}",
        )

    def verify_signature(self, secret_key: bytes) -> bool:
        sign_payload = json.dumps(
            {
                "session_id": self.session_id,
                "tool_name": self.tool_intent.tool_name,
                "args": self.tool_intent.literal_arguments,
            },
            sort_keys=True,
        )
        expected = "sha256=" + hmac.new(secret_key, sign_payload.encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(self.cryptographic_signature, expected)

    def is_expired(self) -> bool:
        return datetime.now(timezone.utc) > self.ttl_timestamp
