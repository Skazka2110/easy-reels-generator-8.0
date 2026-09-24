from __future__ import annotations

import os
import platform
import random
import re
import subprocess
import uuid
from pathlib import Path

from .errors import RenderError
from .media import MediaProbe
from .models import MediaInfo, SubhookAnimation
from .subprocess_utils import hidden_process_kwargs


OUTPUT_DURATION = 6.0
OUTPUT_FPS = 30
OUTPUT_WIDTH = 1080
OUTPUT_HEIGHT = 1920


class VideoRenderer:
    def __init__(
        self,
        ffmpeg: str = "ffmpeg",
        ffprobe: str = "ffprobe",
        encoder: str | None = None,
    ):
        self.ffmpeg = ffmpeg
        self.probe = MediaProbe(ffprobe)
        self.encoder = encoder or self._default_encoder()

    @staticmethod
    def _default_encoder() -> str:
        system = platform.system().lower()
        if system == "windows":
            return "h264_mf"
        if system == "darwin":
            return "h264_videotoolbox"
        return "libx264"

    def validate_environment(self) -> None:
        try:
            process = subprocess.run(
                [self.ffmpeg, "-hide_banner", "-encoders"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
                **hidden_process_kwargs(),
            )
        except FileNotFoundError as exc:
            raise RenderError("FFmpeg не найден в комплекте приложения.") from exc
        if process.returncode != 0:
            raise RenderError("Не удалось получить список кодировщиков FFmpeg.")
        if not re.search(rf"\b{re.escape(self.encoder)}\b", process.stdout):
            raise RenderError(
                f"FFmpeg не содержит требуемый H.264-кодировщик {self.encoder}."
            )

    @staticmethod
    def choose_start(
        duration: float, rng: random.Random, *, random_fragment: bool = True
    ) -> float:
        if duration <= OUTPUT_DURATION or not random_fragment:
            return 0.0
        return rng.uniform(0.0, max(0.0, duration - OUTPUT_DURATION))

    def _input_args(
        self,
        info: MediaInfo,
        start: float,
        *,
        image: bool = False,
    ) -> list[str]:
        if image:
            return ["-loop", "1", "-framerate", str(OUTPUT_FPS), "-i", str(info.path)]
        args: list[str] = []
        if info.duration < OUTPUT_DURATION:
            args.extend(["-stream_loop", "-1"])
        if start > 0:
            args.extend(["-ss", f"{start:.6f}"])
        args.extend(["-i", str(info.path)])
        return args

    def render(
        self,
        video: MediaInfo,
        music: MediaInfo | None,
        overlay_path: str | Path,
        output_path: str | Path,
        *,
        rng: random.Random,
        music_loudness_lufs: float,
        random_music_fragment: bool,
        subhook_overlay_path: str | Path | None = None,
        subhook_x: int = 0,
        subhook_y: int = 0,
        subhook_width: int = 0,
        subhook_height: int = 0,
        subhook_animation: SubhookAnimation = SubhookAnimation.NONE,
        subhook_appear_at: float = 3.0,
    ) -> tuple[float, float]:
        self.validate_environment()
        overlay_path = Path(overlay_path)
        subhook_overlay = (
            Path(subhook_overlay_path) if subhook_overlay_path else None
        )
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        video_start = self.choose_start(video.duration, rng)
        music_start = (
            self.choose_start(
                music.duration, rng, random_fragment=random_music_fragment
            )
            if music
            else 0.0
        )
        temp_output = overlay_path.parent / f"render-{uuid.uuid4().hex}.mp4"

        command = [self.ffmpeg, "-hide_banner", "-loglevel", "error", "-y"]
        command.extend(self._input_args(video, video_start))
        overlay_info = MediaInfo(
            path=overlay_path,
            duration=OUTPUT_DURATION,
            width=OUTPUT_WIDTH,
            height=OUTPUT_HEIGHT,
            has_video=True,
        )
        command.extend(self._input_args(overlay_info, 0.0, image=True))
        subhook_input_index: int | None = None
        if subhook_overlay:
            subhook_input_index = 2
            subhook_info = MediaInfo(
                path=subhook_overlay,
                duration=OUTPUT_DURATION,
                width=subhook_width,
                height=subhook_height,
                has_video=True,
            )
            command.extend(self._input_args(subhook_info, 0.0, image=True))
        audio_input_index = 3 if subhook_overlay else 2
        if music:
            command.extend(self._input_args(music, music_start))
        else:
            command.extend(
                [
                    "-f",
                    "lavfi",
                    "-i",
                    "anullsrc=channel_layout=stereo:sample_rate=48000",
                ]
            )

        video_filters = [
            f"[0:v]scale={OUTPUT_WIDTH}:{OUTPUT_HEIGHT}:"
            "force_original_aspect_ratio=increase:flags=lanczos,"
            f"crop={OUTPUT_WIDTH}:{OUTPUT_HEIGHT},fps={OUTPUT_FPS},"
            "setsar=1,format=yuv420p[base]",
            "[base][1:v]overlay=0:0:format=auto[hooked]",
        ]
        if subhook_input_index is None:
            video_filters.append("[hooked]null[vout]")
        elif subhook_animation == SubhookAnimation.SLIDE_BOUNCE:
            start = subhook_appear_at
            first_end = start + 0.26
            second_end = start + 0.41
            third_end = start + 0.56
            travel = max(220, subhook_height + 120)
            start_y = subhook_y + travel
            overshoot_y = subhook_y - 18
            settle_y = subhook_y + 7
            y_expression = (
                f"if(lt(t,{start:.3f}),{start_y},"
                f"if(lt(t,{first_end:.3f}),"
                f"{start_y}+({overshoot_y - start_y})*(t-{start:.3f})/0.260,"
                f"if(lt(t,{second_end:.3f}),"
                f"{overshoot_y}+({settle_y - overshoot_y})*"
                f"(t-{first_end:.3f})/0.150,"
                f"if(lt(t,{third_end:.3f}),"
                f"{settle_y}+({subhook_y - settle_y})*"
                f"(t-{second_end:.3f})/0.150,{subhook_y}))))"
            )
            video_filters.append(
                f"[hooked][{subhook_input_index}:v]overlay="
                f"x={subhook_x}:y='{y_expression}':"
                f"enable='gte(t,{start:.3f})':format=auto[vout]"
            )
        elif subhook_animation == SubhookAnimation.ZOOM_BOUNCE:
            start = subhook_appear_at
            first_end = start + 0.22
            second_end = start + 0.36
            third_end = start + 0.52
            factor = (
                f"if(lt(t,{start:.3f}),0.05,"
                f"if(lt(t,{first_end:.3f}),"
                f"0.05+1.10*(t-{start:.3f})/0.220,"
                f"if(lt(t,{second_end:.3f}),"
                f"1.15-0.21*(t-{first_end:.3f})/0.140,"
                f"if(lt(t,{third_end:.3f}),"
                f"0.94+0.06*(t-{second_end:.3f})/0.160,1.0))))"
            )
            scaled_width = f"max(2,trunc(iw*({factor})/2)*2)"
            scaled_height = f"max(2,trunc(ih*({factor})/2)*2)"
            video_filters.append(
                f"[{subhook_input_index}:v]format=rgba,"
                f"scale=w='{scaled_width}':h='{scaled_height}':eval=frame"
                "[subhook_animated]"
            )
            video_filters.append(
                "[hooked][subhook_animated]overlay="
                f"x='{subhook_x}+({subhook_width}-overlay_w)/2':"
                f"y='{subhook_y}+({subhook_height}-overlay_h)/2':"
                f"enable='gte(t,{start:.3f})':format=auto[vout]"
            )
        else:
            video_filters.append(
                f"[hooked][{subhook_input_index}:v]overlay="
                f"x={subhook_x}:y={subhook_y}:format=auto[vout]"
            )
        video_filter = ";".join(video_filters)
        if music:
            audio_filter = (
                f"[{audio_input_index}:a]atrim=duration={OUTPUT_DURATION},asetpts=N/SR/TB,"
                "afade=t=in:st=0:d=0.25,"
                f"afade=t=out:st={OUTPUT_DURATION - 0.25}:d=0.25,"
                f"loudnorm=I={music_loudness_lufs:g}:TP=-1:LRA=11,"
                "aresample=48000[aout]"
            )
        else:
            audio_filter = (
                f"[{audio_input_index}:a]atrim=duration={OUTPUT_DURATION},asetpts=N/SR/TB,"
                "aresample=48000[aout]"
            )
        command.extend(
            [
                "-filter_complex",
                f"{video_filter};{audio_filter}",
                "-map",
                "[vout]",
                "-map",
                "[aout]",
                "-t",
                f"{OUTPUT_DURATION:.3f}",
                "-r",
                str(OUTPUT_FPS),
                "-c:v",
                self.encoder,
                "-b:v",
                "8M",
                "-maxrate",
                "10M",
                "-bufsize",
                "16M",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                "-ar",
                "48000",
                "-ac",
                "2",
                "-movflags",
                "+faststart",
                str(temp_output),
            ]
        )
        output_index = len(command) - 1
        if self.encoder != "h264_mf":
            command[output_index:output_index] = ["-profile:v", "main"]
            output_index += 2
        if self.encoder == "libx264":
            command[output_index:output_index] = ["-preset", "veryfast"]

        try:
            process = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
                timeout=900,
                **hidden_process_kwargs(),
            )
            if process.returncode != 0:
                detail = process.stderr.strip() or "FFmpeg завершился с ошибкой"
                command_text = subprocess.list2cmdline(command)
                raise RenderError(
                    "Не удалось создать ролик. Подробности сохранены в папке logs.",
                    technical_detail=f"Команда FFmpeg:\n{command_text}\n\nОшибка FFmpeg:\n{detail}",
                )
            self._verify(temp_output)
            os.replace(temp_output, output_path)
        except FileNotFoundError as exc:
            raise RenderError("FFmpeg не найден в комплекте приложения.") from exc
        except subprocess.TimeoutExpired as exc:
            raise RenderError("Рендер одного ролика превысил допустимое время.") from exc
        except OSError as exc:
            raise RenderError(f"Не удалось записать готовый файл: {exc}") from exc
        finally:
            try:
                if temp_output.exists():
                    temp_output.unlink()
                for leftover in output_path.parent.glob(
                    f".{output_path.stem}.erg-*.mp4"
                ):
                    leftover.unlink()
            except OSError:
                pass
        return video_start, music_start

    def _verify(self, path: Path) -> None:
        info = self.probe.probe(path)
        if not info.has_video or not info.has_audio:
            raise RenderError("Проверка результата: отсутствует видео- или аудиодорожка.")
        if info.width != OUTPUT_WIDTH or info.height != OUTPUT_HEIGHT:
            raise RenderError(
                f"Проверка результата: получено {info.width}×{info.height} вместо 1080×1920."
            )
        tolerance = 1 / OUTPUT_FPS + 0.01
        if abs(info.duration - OUTPUT_DURATION) > tolerance:
            raise RenderError(
                f"Проверка результата: длительность {info.duration:.3f} с вместо 6.000 с."
            )
