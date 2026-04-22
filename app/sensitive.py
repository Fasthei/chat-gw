from __future__ import annotations

import re
from typing import Any

_SENSITIVE_RE = re.compile(
    r"(password|token|secret|api[_\-]?key|authorization|credential)",
    re.IGNORECASE,
)


def scan_sensitive_fields(value: Any, prefix: str = "") -> list[str]:
    """Recursively collect dotted keys whose names match sensitive patterns.

    Walks dicts and lists; leaves non-container values unexamined (we tag on
    key names, not values). Used for audit indexing only — arguments are still
    logged as full original JSON.
    """
    hits: list[str] = []
    _walk(value, prefix, hits)
    return hits


def _walk(value: Any, prefix: str, hits: list[str]) -> None:
    if isinstance(value, dict):
        for key, sub in value.items():
            full_key = f"{prefix}.{key}" if prefix else str(key)
            if isinstance(key, str) and _SENSITIVE_RE.search(key):
                hits.append(full_key)
            _walk(sub, full_key, hits)
    elif isinstance(value, list):
        for idx, sub in enumerate(value):
            _walk(sub, f"{prefix}[{idx}]", hits)
