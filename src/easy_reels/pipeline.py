from __future__ import annotations

import json
import random
import secrets
import tempfile
import traceback
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .config import load_settings
from .control import BatchResult, ProgressCallback, ProgressUpdate, StopToken
from .errors import MediaError, ProjectError, RenderError, TextLayoutError
from .excel import HooksWorkbook
from .media import AUDIO_EXTENSIONS, VIDEO_EXTENSIONS, MediaProbe, discover_files
from .models import AppSettings, HookRow, MediaInfo, MusicFragment, RenderResult
from .naming import output_path
from .paths import ProjectPaths
from .queueing import CyclicShuffledQueue
from .renderer import OUTPUT_DURATION, VideoRenderer
from .text_overlay import render_text_overlay
from .transaction import TransactionJournal


@dataclass(frozen=True, slots=True)
class PreflightReport:
    pending_row: int | None
    pending_rows: int
    valid_videos: int
    valid_music: int
    silent_mode: bool
    warnings: tuple[str, ...]


class ReelsPipeline:
    def __init__(
        self,
        root: str | Path,
        *,
        ffmpeg: str = "ffmpeg",
        ffprobe: str = "ffprobe",
        encoder: str | None = None,
    ):
        self.paths = ProjectPaths.from_root(root)
        self.probe = MediaProbe(ffprobe)
        self.renderer = VideoRenderer(ffmpeg, ffprobe, encoder)
        self.journal = TransactionJournal(self.paths.logs / "pending-transaction.json")

    def _load_inputs(self):
        self.paths.ensure_directories()
        self.paths.cleanup_temporary_outputs()
        self.paths.require_core_files()
        settings = load_settings(self.paths.settings)
        workbook = HooksWorkbook(self.paths.workbook)
        return settings, workbook

    def _validate_fonts(self, settings) -> None:
        missing = [
            name
            for name in {settings.hook.font, settings.subhook.font}
            if not (self.paths.fonts / name).is_file()
        ]
        if missing:
            raise ProjectError(
                "В папке fonts отсутствуют выбранные шрифты: " + ", ".join(sorted(missing))
            )

    def _media(
        self, settings: AppSettings
    ) -> tuple[list[MediaInfo], list[MediaInfo], list[str], bool]:
        video_directory = self.paths.videos_for_position(
            settings.general.hook_position
        )
        video_paths = discover_files(video_directory, VIDEO_EXTENSIONS)
        root_video_paths = discover_files(self.paths.videos, VIDEO_EXTENSIONS)
        relative_directory = video_directory.relative_to(self.paths.root).as_posix()
        if not video_paths:
            root_hint = (
                " Файлы непосредственно в папке videos не используются: "
                f"переместите их в {relative_directory}."
                if root_video_paths
                else ""
            )
            raise MediaError(
                f"В папке {relative_directory} нет поддерживаемых видеофайлов."
                + root_hint
            )
        videos, warnings = self.probe.valid_media(video_paths, require_video=True)
        if root_video_paths:
            warnings.insert(
                0,
                "Файлы непосредственно в папке videos пропущены. "
                f"Для текущей настройки используется только {relative_directory}.",
            )
        if not videos:
            raise MediaError(
                f"В папке {relative_directory} нет ни одного читаемого видеофайла."
            )

        music_paths = discover_files(self.paths.music, AUDIO_EXTENSIONS)
        silent_mode = not music_paths
        music: list[MediaInfo] = []
        if music_paths:
            music, music_warnings = self.probe.valid_media(
                music_paths, require_audio=True
            )
            warnings.extend(music_warnings)
            if not music:
                raise MediaError(
                    "В папке music есть файлы, но ни один из них не содержит читаемой аудиодорожки."
                )
        return videos, music, warnings, silent_mode

    def check(self) -> PreflightReport:
        settings, workbook = self._load_inputs()
        self._validate_fonts(settings)
        self.renderer.validate_environment()
        rows = workbook.pending_rows(record_errors=False)
        videos, music, warnings, silent_mode = self._media(settings)
        return PreflightReport(
            pending_row=rows[0].row_number if rows else None,
            pending_rows=len(rows),
            valid_videos=len(videos),
            valid_music=len(music),
            silent_mode=silent_mode,
            warnings=tuple(warnings),
        )

    def _recover_transaction(self, workbook: HooksWorkbook) -> None:
        pending = self.journal.read()
        if not pending:
            return
        output = Path(pending.get("output_path", ""))
        row_number = pending.get("row_number")
        if output.is_file() and isinstance(row_number, int):
            workbook.mark_success(row_number, output.name)
            workbook.save()
        self.journal.clear()

    def render_one(self, *, seed: int | None = None) -> RenderResult:
        settings, workbook = self._load_inputs()
        self._recover_transaction(workbook)
        self._validate_fonts(settings)
        self.renderer.validate_environment()
        backup = workbook.create_backup(self.paths.backups)
        row = workbook.next_pending()
        if workbook.dirty:
            workbook.save()
        if row is None:
            raise ProjectError("В hooks.xlsx нет необработанных строк с хуком.")

        videos, music, warnings, _silent_mode = self._media(settings)
        actual_seed = seed if seed is not None else secrets.randbits(64)
        rng = random.Random(actual_seed)
        video_queue = CyclicShuffledQueue(videos, rng)
        music_queue = CyclicShuffledQueue(music, rng) if music else None
        video = video_queue.next()
        selected_music = music_queue.next() if music_queue else None
        try:
            result = self._render_row(
                settings=settings,
                workbook=workbook,
                row=row,
                video=video,
                music=selected_music,
                rng=rng,
                backup=backup,
                master_seed=actual_seed,
            )
        except (TextLayoutError, RenderError, MediaError) as exc:
            workbook.mark_error(row.row_number, str(exc))
            workbook.save()
            self.journal.clear()
            self._write_error_log(
                "single_render",
                exc,
                row_number=row.row_number,
                source_video=str(video.path),
                source_music=str(selected_music.path) if selected_music else None,
            )
            raise
        self._write_run_log(result, actual_seed, warnings)
        return result

    def run_batch(
        self,
        *,
        seed: int | None = None,
        progress: ProgressCallback | None = None,
        stop_token: StopToken | None = None,
    ) -> BatchResult:
        settings, workbook = self._load_inputs()
        self._recover_transaction(workbook)
        self._validate_fonts(settings)
        self.renderer.validate_environment()
        backup = workbook.create_backup(self.paths.backups)
        rows = workbook.pending_rows()
        if workbook.dirty:
            workbook.save()
        if not rows:
            raise ProjectError("В hooks.xlsx нет необработанных строк с хуком.")

        videos, music, warnings, _silent_mode = self._media(settings)
        actual_seed = seed if seed is not None else secrets.randbits(64)
        rng = random.Random(actual_seed)
        video_queue = CyclicShuffledQueue(videos, rng)
        music_queue = CyclicShuffledQueue(music, rng) if music else None
        token = stop_token or StopToken()
        created: list[str] = []
        errors: list[tuple[int, str]] = []
        processed = 0
        stopped = False
        total = len(rows)

        self._emit(
            progress,
            ProgressUpdate(
                phase="preflight",
                processed=0,
                total=total,
                created=0,
                errors=0,
                row_number=None,
                message=f"Проверка завершена. К созданию: {total}.",
            ),
        )
        for row in rows:
            if token.requested:
                stopped = True
                break
            video = video_queue.next()
            selected_music = music_queue.next() if music_queue else None
            self._emit(
                progress,
                ProgressUpdate(
                    phase="rendering",
                    processed=processed,
                    total=total,
                    created=len(created),
                    errors=len(errors),
                    row_number=row.row_number,
                    message=f"Создаётся ролик {processed + 1} из {total}.",
                ),
            )
            try:
                result = self._render_row(
                    settings=settings,
                    workbook=workbook,
                    row=row,
                    video=video,
                    music=selected_music,
                    rng=rng,
                    backup=backup,
                    master_seed=actual_seed,
                )
            except (TextLayoutError, RenderError, MediaError) as exc:
                message = " ".join(str(exc).split())
                workbook.mark_error(row.row_number, message)
                workbook.save()
                self.journal.clear()
                self._write_error_log(
                    "batch_render",
                    exc,
                    row_number=row.row_number,
                    source_video=str(video.path),
                    source_music=str(selected_music.path) if selected_music else None,
                )
                errors.append((row.row_number, message))
                processed += 1
                self._emit(
                    progress,
                    ProgressUpdate(
                        phase="row_error",
                        processed=processed,
                        total=total,
                        created=len(created),
                        errors=len(errors),
                        row_number=row.row_number,
                        message=f"Строка {row.row_number}: {message}",
                    ),
                )
                continue

            created.append(str(result.output_path))
            processed += 1
            self._write_run_log(result, actual_seed, warnings)
            self._emit(
                progress,
                ProgressUpdate(
                    phase="saved",
                    processed=processed,
                    total=total,
                    created=len(created),
                    errors=len(errors),
                    row_number=row.row_number,
                    message=f"Готово {processed} из {total}.",
                ),
            )

        if token.requested and processed < total:
            stopped = True
        phase = "stopped" if stopped else "completed"
        message = (
            f"Остановлено после {processed} из {total}."
            if stopped
            else f"Завершено: {len(created)} роликов, ошибок: {len(errors)}."
        )
        self._emit(
            progress,
            ProgressUpdate(
                phase=phase,
                processed=processed,
                total=total,
                created=len(created),
                errors=len(errors),
                row_number=None,
                message=message,
            ),
        )
        result = BatchResult(
            total=total,
            processed=processed,
            created_files=tuple(created),
            row_errors=tuple(errors),
            stopped=stopped,
        )
        self._write_batch_log(result, actual_seed, warnings)
        return result

    def render_preview(self, *, seed: int | None = None) -> RenderResult:
        try:
            return self._render_preview(seed=seed)
        except Exception as exc:
            try:
                self.paths.ensure_directories()
                self._write_error_log("preview", exc)
            except OSError:
                pass
            raise

    def _render_preview(self, *, seed: int | None = None) -> RenderResult:
        settings, workbook = self._load_inputs()
        self._validate_fonts(settings)
        self.renderer.validate_environment()
        rows = workbook.pending_rows(record_errors=False)
        if not rows:
            raise ProjectError("В hooks.xlsx нет строки с хуком для предпросмотра.")
        videos, music, warnings, _silent_mode = self._media(settings)
        row = rows[0]
        video = videos[0]
        selected_music = music[0] if music else None
        actual_seed = seed if seed is not None else secrets.randbits(64)
        rng = random.Random(actual_seed)
        destination = self._next_preview_path()
        with tempfile.TemporaryDirectory(prefix="erg-preview-", dir=self.paths.logs) as temporary:
            overlay = Path(temporary) / "overlay.png"
            subhook_overlay = Path(temporary) / "subhook.png"
            layers = render_text_overlay(
                row.hook,
                row.subhook,
                settings,
                self.paths.fonts,
                overlay,
                seed=actual_seed,
                subhook_output_path=subhook_overlay,
            )
            video_start, music_start = self.renderer.render(
                video,
                selected_music,
                overlay,
                destination,
                rng=rng,
                music_loudness_lufs=settings.general.music_loudness_lufs,
                random_music_fragment=(
                    settings.general.music_fragment == MusicFragment.RANDOM
                ),
                subhook_overlay_path=layers.subhook_path,
                subhook_x=layers.subhook_x,
                subhook_y=layers.subhook_y,
                subhook_width=layers.subhook_width,
                subhook_height=layers.subhook_height,
                subhook_animation=settings.subhook_animation.animation,
                subhook_appear_at=settings.subhook_animation.appear_at,
            )
        result = RenderResult(
            row_number=row.row_number,
            output_path=destination,
            source_video=video.path,
            source_music=selected_music.path if selected_music else None,
            video_start=video_start,
            music_start=music_start,
            duration=OUTPUT_DURATION,
        )
        self._write_run_log(result, actual_seed, warnings, operation="preview")
        return result

    def _next_preview_path(self) -> Path:
        """Return a new path so an open older preview never blocks a test."""
        stem = datetime.now().strftime("preview_%Y-%m-%d_%H%M%S")
        candidate = self.paths.preview / f"{stem}.mp4"
        suffix = 2
        while candidate.exists():
            candidate = self.paths.preview / f"{stem}_{suffix}.mp4"
            suffix += 1
        return candidate

    def _render_row(
        self,
        *,
        settings: AppSettings,
        workbook: HooksWorkbook,
        row: HookRow,
        video: MediaInfo,
        music: MediaInfo | None,
        rng: random.Random,
        backup: Path,
        master_seed: int,
    ) -> RenderResult:
        destination = output_path(self.paths.ready, row.row_number, row.hook)
        overlay_seed = rng.getrandbits(64)
        journal_payload = {
            "stage": "planned",
            "row_number": row.row_number,
            "output_path": str(destination),
            "backup_path": str(backup),
            "seed": master_seed,
        }
        self.journal.write(journal_payload)
        with tempfile.TemporaryDirectory(prefix="erg-render-", dir=self.paths.logs) as temporary:
            overlay = Path(temporary) / "overlay.png"
            subhook_overlay = Path(temporary) / "subhook.png"
            layers = render_text_overlay(
                row.hook,
                row.subhook,
                settings,
                self.paths.fonts,
                overlay,
                seed=overlay_seed,
                subhook_output_path=subhook_overlay,
            )
            video_start, music_start = self.renderer.render(
                video,
                music,
                overlay,
                destination,
                rng=rng,
                music_loudness_lufs=settings.general.music_loudness_lufs,
                random_music_fragment=(
                    settings.general.music_fragment == MusicFragment.RANDOM
                ),
                subhook_overlay_path=layers.subhook_path,
                subhook_x=layers.subhook_x,
                subhook_y=layers.subhook_y,
                subhook_width=layers.subhook_width,
                subhook_height=layers.subhook_height,
                subhook_animation=settings.subhook_animation.animation,
                subhook_appear_at=settings.subhook_animation.appear_at,
            )
        journal_payload["stage"] = "file_committed"
        self.journal.write(journal_payload)
        workbook.mark_success(row.row_number, destination.name)
        workbook.save()
        self.journal.clear()
        return RenderResult(
            row_number=row.row_number,
            output_path=destination,
            source_video=video.path,
            source_music=music.path if music else None,
            video_start=video_start,
            music_start=music_start,
            duration=OUTPUT_DURATION,
        )

    @staticmethod
    def _emit(callback: ProgressCallback | None, update: ProgressUpdate) -> None:
        if callback:
            callback(update)

    def _write_run_log(
        self,
        result: RenderResult,
        seed: int,
        warnings: list[str],
        *,
        operation: str = "render",
    ) -> None:
        timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S_%f")
        path = self.paths.logs / f"render_{timestamp}.json"
        payload = {
            "operation": operation,
            "seed": seed,
            "row_number": result.row_number,
            "output_path": str(result.output_path),
            "source_video": str(result.source_video),
            "source_music": str(result.source_music) if result.source_music else None,
            "video_start": result.video_start,
            "music_start": result.music_start,
            "duration": result.duration,
            "warnings": warnings,
        }
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def _write_error_log(self, operation: str, exc: Exception, **context) -> None:
        timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S_%f")
        path = self.paths.logs / f"error_{timestamp}.json"
        technical_detail = getattr(exc, "technical_detail", None)
        payload = {
            "operation": operation,
            "error_type": type(exc).__name__,
            "user_message": str(exc),
            "technical_detail": technical_detail or traceback.format_exc(),
            "context": context,
        }
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def _write_batch_log(
        self, result: BatchResult, seed: int, warnings: list[str]
    ) -> None:
        timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S_%f")
        path = self.paths.logs / f"batch_{timestamp}.json"
        payload = {
            "seed": seed,
            "total": result.total,
            "processed": result.processed,
            "created_files": list(result.created_files),
            "row_errors": [list(error) for error in result.row_errors],
            "stopped": result.stopped,
            "warnings": warnings,
        }
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
