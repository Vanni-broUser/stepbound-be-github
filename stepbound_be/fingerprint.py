"""Groups error reports that are the same bug.

The summary line of the error, with numbers and quoted values blanked (an
index out of range at 7 and at 12 are one bug), plus the first frames of
the stack that belong to the game."""

from __future__ import annotations

import hashlib
import re

_NUMBER = re.compile(r"\b\d+(\.\d+)?\b")
_QUOTED = re.compile(r"(['\"]).*?\1")
_HEX = re.compile(r"\b0x[0-9a-fA-F]+\b")
_FRAME = re.compile(r"^#\d+\s+(\S.*?)\s+\((package:stepbound/[^:)]+)", re.M)


def normalize(summary: str) -> str:
    text = _HEX.sub("#", summary)
    text = _QUOTED.sub("'…'", text)
    text = _NUMBER.sub("#", text)
    return " ".join(text.split())[:300]


def game_frames(body: str, limit: int = 3) -> list[str]:
    return [f"{fn} {file}" for fn, file in _FRAME.findall(body)[:limit]]


def fingerprint(source: str, summary: str, body: str) -> str:
    key = "\n".join([source.split(":")[0], normalize(summary), *game_frames(body)])
    return hashlib.sha256(key.encode("utf-8")).hexdigest()
