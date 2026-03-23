import logging
import sys
from pathlib import Path

import yaml
from pydantic import ValidationError

from app.models.entities import EntityManifestModel

logger = logging.getLogger("grimoire.entity_loader")


def _build_copilot_manifest() -> EntityManifestModel:
    return EntityManifestModel(
        entity_id="copilot-introspector",
        name="Copilot",
        priority=90,
        tier_lock=1,
        bind_domains=["meta_orchestration"],
        role="introspector",
        critic_constitution={"bind_domains": ["meta_orchestration"]},
    )


def load_and_validate_entities(entities_path: Path) -> dict[str, EntityManifestModel]:
    entities: dict[str, EntityManifestModel] = {}
    yaml_files = sorted(list(entities_path.glob("*.yaml")) + list(entities_path.glob("*.yml")))

    if not yaml_files:
        logger.warning("Nenhum manifesto encontrado em %s", entities_path)
        entities["copilot-introspector"] = _build_copilot_manifest()
        return entities

    errors: list[str] = []
    for yaml_file in yaml_files:
        try:
            raw = yaml.safe_load(yaml_file.read_text(encoding="utf-8"))
            entity = EntityManifestModel.model_validate(raw)
            entities[entity.entity_id] = entity
            logger.info("Entidade carregada: %s (prioridade: %s)", entity.name, entity.priority)
        except (yaml.YAMLError, ValidationError, TypeError) as exc:
            errors.append(f"{yaml_file.name}: {exc}")

    if errors:
        logger.critical("BOOT ABORTADO — Manifestos YAML inválidos detectados:")
        for err in errors:
            logger.critical("  %s", err)
        logger.critical("Corrija os manifestos antes de reiniciar o servidor.")
        sys.exit(1)

    if "copilot-introspector" not in entities:
        entities["copilot-introspector"] = _build_copilot_manifest()
    return entities
