from __future__ import annotations

import random
from collections.abc import Sequence
from typing import Generic, TypeVar

from .errors import MediaError


T = TypeVar("T")


class CyclicShuffledQueue(Generic[T]):
    def __init__(self, items: Sequence[T], rng: random.Random):
        if not items:
            raise MediaError("Невозможно создать пустую очередь медиафайлов.")
        self._items = list(items)
        rng.shuffle(self._items)
        self._index = 0

    @property
    def order(self) -> tuple[T, ...]:
        return tuple(self._items)

    def next(self) -> T:
        value = self._items[self._index]
        self._index = (self._index + 1) % len(self._items)
        return value

