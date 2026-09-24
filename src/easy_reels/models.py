from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path


class HookPosition(StrEnum):
    TOP = "top"
    BOTTOM = "bottom"


class MusicFragment(StrEnum):
    START = "start"
    RANDOM = "random"


class BackgroundStyle(StrEnum):
    NONE = "none"
    RECTANGLE = "rectangle"
    LINES = "lines"
    OUTLINE = "outline"
    GLOW = "glow"
    TORN_PAPER = "torn_paper"
    PAPER_LETTERS = "paper_letters"


class SubhookAnimation(StrEnum):
    NONE = "none"
    SLIDE_BOUNCE = "slide_bounce"
    ZOOM_BOUNCE = "zoom_bounce"


@dataclass(frozen=True, slots=True)
class GeneralSettings:
    hook_position: HookPosition
    music_fragment: MusicFragment
    music_loudness_lufs: float


@dataclass(frozen=True, slots=True)
class TextStyleSettings:
    font: str
    font_size: int
    text_color: str
    outline_width: int
    outline_color: str
    background_style: BackgroundStyle
    background_color: str
    background_opacity: int
    background_padding: int
    background_corner_radius: int
    glow_color: str = "#FFFFFF"
    glow_opacity: int = 80
    glow_radius: int = 18


@dataclass(frozen=True, slots=True)
class SubhookAnimationSettings:
    animation: SubhookAnimation = SubhookAnimation.NONE
    appear_at: float = 3.0


@dataclass(frozen=True, slots=True)
class AppSettings:
    general: GeneralSettings
    hook: TextStyleSettings
    subhook: TextStyleSettings
    subhook_animation: SubhookAnimationSettings = field(
        default_factory=SubhookAnimationSettings
    )


@dataclass(frozen=True, slots=True)
class TextOverlayLayers:
    hook_path: Path
    subhook_path: Path | None = None
    subhook_x: int = 0
    subhook_y: int = 0
    subhook_width: int = 0
    subhook_height: int = 0


@dataclass(frozen=True, slots=True)
class HookRow:
    row_number: int
    hook: str
    subhook: str
    description: str


@dataclass(frozen=True, slots=True)
class HookEditorRow:
    """One row shown in the built-in hooks editor."""

    hook: str = ""
    subhook: str = ""
    description: str = ""
    ready_file: str = ""
    status: str = ""


@dataclass(frozen=True, slots=True)
class MediaInfo:
    path: Path
    duration: float
    width: int | None = None
    height: int | None = None
    has_video: bool = False
    has_audio: bool = False


@dataclass(frozen=True, slots=True)
class RenderResult:
    row_number: int
    output_path: Path
    source_video: Path
    source_music: Path | None
    video_start: float
    music_start: float
    duration: float
