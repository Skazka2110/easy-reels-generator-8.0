from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .errors import ProjectError
from .models import HookPosition


@dataclass(frozen=True, slots=True)
class ProjectPaths:
    root: Path

    @classmethod
    def from_root(cls, root: str | Path) -> "ProjectPaths":
        return cls(Path(root).expanduser().resolve())

    @property
    def workbook(self) -> Path:
        return self.root / "hooks.xlsx"

    @property
    def settings(self) -> Path:
        return self.root / "settings.ini"

    @property
    def videos(self) -> Path:
        return self.root / "videos"

    @property
    def videos_top(self) -> Path:
        return self.videos / "top"

    @property
    def videos_bottom(self) -> Path:
        return self.videos / "bottom"

    def videos_for_position(self, position: HookPosition) -> Path:
        if position == HookPosition.TOP:
            return self.videos_top
        return self.videos_bottom

    @property
    def music(self) -> Path:
        return self.root / "music"

    @property
    def fonts(self) -> Path:
        return self.root / "fonts"

    @property
    def overlays(self) -> Path:
        return self.root / "overlays"

    @property
    def ready(self) -> Path:
        return self.root / "ready"

    @property
    def preview(self) -> Path:
        return self.root / "preview"

    @property
    def logs(self) -> Path:
        return self.root / "logs"

    @property
    def backups(self) -> Path:
        return self.root / "backups"

    @property
    def licenses(self) -> Path:
        return self.root / "licenses"

    def ensure_directories(self) -> None:
        try:
            self.root.mkdir(parents=True, exist_ok=True)
            for directory in (
                self.videos,
                self.videos_top,
                self.videos_bottom,
                self.music,
                self.fonts,
                self.overlays,
                self.ready,
                self.preview,
                self.logs,
                self.backups,
                self.licenses,
            ):
                directory.mkdir(exist_ok=True)
        except OSError as exc:
            raise ProjectError(
                f"Не удалось создать рабочие папки в «{self.root}»: {exc}"
            ) from exc

    def require_core_files(self) -> None:
        missing = [path.name for path in (self.workbook, self.settings) if not path.is_file()]
        if missing:
            raise ProjectError(
                "В папке проекта отсутствуют обязательные файлы: " + ", ".join(missing)
            )

    def cleanup_temporary_outputs(self) -> None:
        for directory in (self.ready, self.preview):
            for path in directory.glob(".*.erg-*.mp4"):
                try:
                    path.unlink()
                except OSError as exc:
                    raise ProjectError(
                        f"Не удалось удалить незавершённый временный файл «{path.name}»: {exc}"
                    ) from exc
