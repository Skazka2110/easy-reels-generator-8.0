from __future__ import annotations

import json
import subprocess
from pathlib import Path

from .errors import MediaError
from .models import MediaInfo
from .subprocess_utils import hidden_process_kwargs


VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".mkv", ".avi", ".webm"}
AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg"}


def discover_files(directory: str | Path, extensions: set[str]) -> list[Path]:
    directory = Path(directory)
    if not directory.exists():
        return []
    return sorted(
        (
            path
            for path in directory.iterdir()
            if path.is_file() and path.suffix.lower() in extensions
        ),
        key=lambda path: path.name.casefold(),
    )


class MediaProbe:
    def __init__(self, executable: str = "ffprobe"):
        self.executable = executable

    def probe(self, path: str | Path) -> MediaInfo:
        path = Path(path)
        command = [
            self.executable,
            "-v",
            "error",
            "-show_entries",
            "format=duration:stream=codec_type,width,height,duration",
            "-of",
            "json",
            str(path),
        ]
        try:
            process = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
                **hidden_process_kwargs(),
            )
        except FileNotFoundError as exc:
            raise MediaError("FFprobe не найден в комплекте приложения.") from exc
        if process.returncode != 0:
            detail = process.stderr.strip() or "неизвестная ошибка FFprobe"
            raise MediaError(f"Файл «{path.name}» не читается: {detail}")
        try:
            payload = json.loads(process.stdout)
            streams = payload.get("streams", [])
            video_stream = next(
                (stream for stream in streams if stream.get("codec_type") == "video"),
                None,
            )
            has_audio = any(
                stream.get("codec_type") == "audio" for stream in streams
            )
            duration_raw = payload.get("format", {}).get("duration")
            if duration_raw in (None, "N/A") and video_stream:
                duration_raw = video_stream.get("duration")
            duration = float(duration_raw)
        except (ValueError, TypeError, StopIteration) as exc:
            raise MediaError(f"Не удалось определить длительность файла «{path.name}».") from exc
        if duration <= 0:
            raise MediaError(f"Файл «{path.name}» имеет нулевую длительность.")
        return MediaInfo(
            path=path,
            duration=duration,
            width=int(video_stream["width"]) if video_stream and video_stream.get("width") else None,
            height=int(video_stream["height"]) if video_stream and video_stream.get("height") else None,
            has_video=video_stream is not None,
            has_audio=has_audio,
        )

    def valid_media(
        self, paths: list[Path], *, require_video: bool = False, require_audio: bool = False
    ) -> tuple[list[MediaInfo], list[str]]:
        valid: list[MediaInfo] = []
        warnings: list[str] = []
        for path in paths:
            try:
                info = self.probe(path)
                if require_video and not info.has_video:
                    raise MediaError(f"В файле «{path.name}» нет видеопотока.")
                if require_audio and not info.has_audio:
                    raise MediaError(f"В файле «{path.name}» нет аудиопотока.")
                valid.append(info)
            except MediaError as exc:
                warnings.append(str(exc))
        return valid, warnings

