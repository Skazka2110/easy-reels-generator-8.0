from __future__ import annotations

import re
import unicodedata
from pathlib import Path


ILLEGAL = re.compile(r"[<>:\"/\\|?*\x00-\x1f]")
SEPARATORS = re.compile(r"[\s_]+")
DASHES = re.compile(r"-+")


def safe_slug(text: str, maximum: int = 100) -> str:
    value = unicodedata.normalize("NFKC", text).lower()
    value = ILLEGAL.sub(" ", value)
    value = "".join(
        character
        for character in value
        if character.isalnum() or character in {" ", "-", "_"}
    )
    value = SEPARATORS.sub("-", value)
    value = DASHES.sub("-", value).strip("-. ")
    if not value:
        value = "reel"
    if len(value) <= maximum:
        return value
    shortened = value[:maximum].rstrip("-")
    if "-" in shortened:
        word_boundary = shortened.rsplit("-", 1)[0]
        if len(word_boundary) >= maximum // 2:
            shortened = word_boundary
    return shortened or "reel"


def output_path(ready_dir: Path, row_number: int, hook: str) -> Path:
    prefix = f"{row_number - 1:03d}"
    base = f"{prefix}_{safe_slug(hook)}"
    candidate = ready_dir / f"{base}.mp4"
    counter = 2
    while candidate.exists():
        candidate = ready_dir / f"{base}_{counter}.mp4"
        counter += 1
    return candidate

