from __future__ import annotations

import json
import os
import uuid
from pathlib import Path

from .errors import ProjectError


class TransactionJournal:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def write(self, payload: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_name(f".{self.path.name}.{uuid.uuid4().hex}.tmp")
        try:
            temp.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            os.replace(temp, self.path)
        except OSError as exc:
            raise ProjectError(f"Не удалось записать журнал транзакции: {exc}") from exc
        finally:
            try:
                if temp.exists():
                    temp.unlink()
            except OSError:
                pass

    def read(self) -> dict | None:
        if not self.path.exists():
            return None
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ProjectError(f"Повреждён журнал транзакции {self.path.name}: {exc}") from exc

    def clear(self) -> None:
        try:
            self.path.unlink(missing_ok=True)
        except OSError as exc:
            raise ProjectError(f"Не удалось закрыть журнал транзакции: {exc}") from exc

