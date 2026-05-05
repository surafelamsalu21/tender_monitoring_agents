"""Shared helpers: strip model fluff, parse JSON arrays from chat responses."""
from __future__ import annotations

import json
import re
from typing import Any, List, Optional

_REASONING_PATTERNS = [
    re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE),
    re.compile(r"<thinking>.*?</thinking>", re.DOTALL | re.IGNORECASE),
    re.compile(r"<reasoning>.*?</reasoning>", re.DOTALL | re.IGNORECASE),
    re.compile(r"<thought>.*?</thought>", re.DOTALL | re.IGNORECASE),
]


def extract_message_text(response: Any) -> str:
    text = getattr(response, "content", None) or ""
    extra = getattr(response, "additional_kwargs", {}) or {}
    for key in ("answer", "response", "output"):
        chunk = extra.get(key)
        if isinstance(chunk, str) and chunk.strip():
            text = chunk.strip()
            break
    return text.strip()


def strip_reasoning(text: str) -> str:
    result = text
    for pattern in _REASONING_PATTERNS:
        result = pattern.sub("", result)
    return result.strip()


def _try_load_bracket_array(text: str) -> Optional[List[Any]]:
    start, end = text.find("["), text.rfind("]")
    if start == -1 or end <= start:
        return None
    try:
        payload = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, list) else None


def _json_root_to_list(payload: Any) -> Optional[List[Any]]:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("opportunities", "items", "tenders", "results", "data", "rows"):
            inner = payload.get(key)
            if isinstance(inner, list):
                return inner
    return None


def _extract_json_block(text: str) -> Optional[Any]:
    if not text:
        return None
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        pass
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n", 1)
        cleaned = lines[1] if len(lines) > 1 else cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3].strip()
    if "```json" in cleaned:
        parts = cleaned.split("```json", 1)
        if len(parts) > 1:
            cleaned = parts[1].split("```", 1)[0].strip()
    elif "```" in cleaned:
        parts = cleaned.split("```", 1)
        if len(parts) > 1:
            cleaned = parts[1].split("```", 1)[0].strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start, end = text.find("["), text.rfind("]")
        if start != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                pass
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                pass
    return None


def parse_json_array(raw: str) -> List[dict]:
    """Best-effort: turn model text into a list of dicts."""
    if not raw:
        return []
    t = raw.strip()
    try:
        payload = json.loads(t)
    except json.JSONDecodeError:
        payload = None
    if payload is not None:
        inner = _json_root_to_list(payload)
        if inner is not None:
            return [x for x in inner if isinstance(x, dict)]
        if isinstance(payload, dict) and payload.get("title") and payload.get("url"):
            return [payload]

    bracket = _try_load_bracket_array(t)
    if bracket is not None:
        return [x for x in bracket if isinstance(x, dict)]

    cleaned = strip_reasoning(raw)
    json_data = _extract_json_block(cleaned)
    if json_data is None:
        return []
    if isinstance(json_data, list):
        return [x for x in json_data if isinstance(x, dict)]
    if isinstance(json_data, dict):
        inner = _json_root_to_list(json_data)
        if inner:
            return [x for x in inner if isinstance(x, dict)]
        if json_data.get("title") and json_data.get("url"):
            return [json_data]
    return []
