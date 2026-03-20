from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class CriticConstitution(BaseModel):
    bind_domains: list[str]
    required_tags: list[str] = []
    dynamic_routing_fallback: bool = False


class KnowledgeGating(BaseModel):
    allowed_namespaces: list[str] = []


class EntityManifestModel(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    entity_id: str
    name: str
    priority: int = Field(..., ge=1, le=100)
    tier_lock: int = Field(..., ge=1, le=3)
    bind_domains: list[str]
    conflict_strategy: Literal[
        "escalate",
        "defer_to_higher",
        "merge_non_contradictory",
    ] = "escalate"
    max_context_tokens: int = Field(default=2000, ge=100, le=8000)
    version: str = "1.0.0"
    role: Literal["standard", "introspector"] = "standard"
    knowledge_gating: KnowledgeGating = KnowledgeGating()
    critic_constitution: CriticConstitution
