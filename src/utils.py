from __future__ import annotations

import json
from typing import Any


def conversation_summary(messages: list[dict[str, Any]]) -> str:
    recent = messages[-6:]
    return "\n".join(f"{msg['role']}: {str(msg.get('content', ''))[:500]}" for msg in recent)


def params_key(params: list[Any]) -> str:
    return json.dumps(params, default=str, ensure_ascii=False)


def schema_allowed_columns(schema: dict[str, Any]) -> set[str]:
    return {col["name"] for col in schema.get("columns", [])}
