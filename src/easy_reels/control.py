from __future__ import annotations

from dataclasses import dataclass
from threading import Event
from typing import Callable


class StopToken:
    """Thread-safe request to stop after the current reel finishes."""

    def __init__(self) -> None:
        self._event = Event()

    def request_stop(self) -> None:
        self._event.set()

    @property
    def requested(self) -> bool:
        return self._event.is_set()


@dataclass(frozen=True, slots=True)
class ProgressUpdate:
    phase: str
    processed: int
    total: int
    created: int
    errors: int
    row_number: int | None
    message: str


ProgressCallback = Callable[[ProgressUpdate], None]


@dataclass(frozen=True, slots=True)
class BatchResult:
    total: int
    processed: int
    created_files: tuple[str, ...]
    row_errors: tuple[tuple[int, str], ...]
    stopped: bool

