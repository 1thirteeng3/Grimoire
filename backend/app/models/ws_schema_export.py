"""
Exporta schema canônico de eventos WebSocket em formato OpenAPI.
Executar: python -m app.models.ws_schema_export > ws_events_schema.json
"""

import json
from typing import Any

from app.models.websocket import ServerEventAdapter


def _rewrite_refs(node: Any) -> Any:
    if isinstance(node, dict):
        rewritten: dict[str, Any] = {}
        for key, value in node.items():
            if key == "$ref" and isinstance(value, str):
                rewritten[key] = value.replace("#/$defs/", "#/components/schemas/")
            else:
                rewritten[key] = _rewrite_refs(value)
        return rewritten
    if isinstance(node, list):
        return [_rewrite_refs(item) for item in node]
    if isinstance(node, str) and node.startswith("#/$defs/"):
        return node.replace("#/$defs/", "#/components/schemas/")
    return node


def export_schema() -> dict[str, Any]:
    raw_schema = ServerEventAdapter.json_schema(mode="serialization")
    defs = raw_schema.pop("$defs", {})
    server_event_schema = _rewrite_refs(raw_schema)
    defs_rewritten = {name: _rewrite_refs(schema) for name, schema in defs.items()}

    return {
        "openapi": "3.1.0",
        "info": {"title": "Grimorio WebSocket Events", "version": "0.1.0"},
        "paths": {},
        "components": {
            "schemas": {
                "ServerEvent": server_event_schema,
                **defs_rewritten,
            }
        },
    }


if __name__ == "__main__":
    print(json.dumps(export_schema(), indent=2))
