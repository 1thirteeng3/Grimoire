import re


def should_shadow(query: str, candidate: str, blocked_patterns: list[str] | None = None) -> bool:
    patterns = blocked_patterns or [r"\brm\s+-rf\b", r"\beval\("]
    text = f"{query}\n{candidate}".lower()
    return any(re.search(pattern, text) for pattern in patterns)
