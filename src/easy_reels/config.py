from __future__ import annotations

import configparser
import re
import tempfile
from pathlib import Path

from .errors import SettingsError
from .models import (
    AppSettings,
    BackgroundStyle,
    GeneralSettings,
    HookPosition,
    MusicFragment,
    SubhookAnimation,
    SubhookAnimationSettings,
    TextStyleSettings,
)


COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")


def _required(parser: configparser.ConfigParser, section: str, option: str) -> str:
    if not parser.has_section(section):
        raise SettingsError(f"В settings.ini отсутствует раздел [{section}].")
    if not parser.has_option(section, option):
        raise SettingsError(f"В settings.ini отсутствует параметр {section}.{option}.")
    return parser.get(section, option).strip()


def _integer(
    parser: configparser.ConfigParser,
    section: str,
    option: str,
    minimum: int,
    maximum: int,
) -> int:
    raw = _required(parser, section, option)
    try:
        value = int(raw)
    except ValueError as exc:
        raise SettingsError(f"Параметр {section}.{option} должен быть целым числом.") from exc
    if not minimum <= value <= maximum:
        raise SettingsError(
            f"Параметр {section}.{option} должен быть от {minimum} до {maximum}."
        )
    return value


def _color(parser: configparser.ConfigParser, section: str, option: str) -> str:
    value = _required(parser, section, option)
    if not COLOR_RE.fullmatch(value):
        raise SettingsError(f"Параметр {section}.{option} должен иметь формат #RRGGBB.")
    return value.upper()


def _optional_integer(
    parser: configparser.ConfigParser,
    section: str,
    option: str,
    minimum: int,
    maximum: int,
    default: int,
) -> int:
    if not parser.has_option(section, option):
        return default
    return _integer(parser, section, option, minimum, maximum)


def _optional_color(
    parser: configparser.ConfigParser,
    section: str,
    option: str,
    default: str,
) -> str:
    if not parser.has_option(section, option):
        return default
    return _color(parser, section, option)


def _optional_float(
    parser: configparser.ConfigParser,
    section: str,
    option: str,
    minimum: float,
    maximum: float,
    default: float,
) -> float:
    if not parser.has_option(section, option):
        return default
    raw = parser.get(section, option).strip()
    try:
        value = float(raw.replace(",", "."))
    except ValueError as exc:
        raise SettingsError(
            f"Параметр {section}.{option} должен быть числом."
        ) from exc
    if not minimum <= value <= maximum:
        raise SettingsError(
            f"Параметр {section}.{option} должен быть от "
            f"{minimum:g} до {maximum:g}."
        )
    return value


def _enum(enum_type, parser: configparser.ConfigParser, section: str, option: str):
    raw = _required(parser, section, option).lower()
    try:
        return enum_type(raw)
    except ValueError as exc:
        allowed = ", ".join(item.value for item in enum_type)
        raise SettingsError(
            f"Неизвестное значение {section}.{option}={raw!r}. Допустимо: {allowed}."
        ) from exc


def _background_style(
    parser: configparser.ConfigParser, section: str
) -> BackgroundStyle:
    raw = _required(parser, section, "background_style").lower()
    # Старое значение contour из версий до 0.6.1 безопасно превращаем
    # в новую обводку букв, чтобы пользовательские настройки не ломались.
    if raw == "contour":
        raw = BackgroundStyle.OUTLINE.value
    try:
        return BackgroundStyle(raw)
    except ValueError as exc:
        allowed = ", ".join(item.value for item in BackgroundStyle)
        raise SettingsError(
            f"Неизвестное значение {section}.background_style={raw!r}. "
            f"Допустимо: {allowed}."
        ) from exc


def _text_style(parser: configparser.ConfigParser, section: str) -> TextStyleSettings:
    font = _required(parser, section, "font")
    if Path(font).name != font or Path(font).suffix.lower() not in {".ttf", ".otf"}:
        raise SettingsError(
            f"Параметр {section}.font должен содержать только имя TTF/OTF-файла."
        )
    return TextStyleSettings(
        font=font,
        font_size=_integer(parser, section, "font_size", 1, 400),
        text_color=_color(parser, section, "text_color"),
        outline_width=_integer(parser, section, "outline_width", 0, 30),
        outline_color=_color(parser, section, "outline_color"),
        background_style=_background_style(parser, section),
        background_color=_color(parser, section, "background_color"),
        background_opacity=_integer(parser, section, "background_opacity", 0, 100),
        background_padding=_integer(parser, section, "background_padding", 0, 200),
        background_corner_radius=_integer(
            parser, section, "background_corner_radius", 0, 200
        ),
        glow_color=_optional_color(
            parser, section, "glow_color", "#FFFFFF"
        ),
        glow_opacity=_optional_integer(
            parser, section, "glow_opacity", 0, 100, 80
        ),
        glow_radius=_optional_integer(
            parser, section, "glow_radius", 1, 100, 18
        ),
    )


def _subhook_animation(
    parser: configparser.ConfigParser,
) -> SubhookAnimationSettings:
    raw = parser.get(
        "subhook", "animation", fallback=SubhookAnimation.NONE.value
    ).strip().lower()
    try:
        animation = SubhookAnimation(raw)
    except ValueError as exc:
        allowed = ", ".join(item.value for item in SubhookAnimation)
        raise SettingsError(
            "Неизвестное значение subhook.animation="
            f"{raw!r}. Допустимо: {allowed}."
        ) from exc
    return SubhookAnimationSettings(
        animation=animation,
        appear_at=_optional_float(
            parser, "subhook", "appear_at", 0.0, 5.5, 3.0
        ),
    )


def _settings_from_parser(parser: configparser.ConfigParser) -> AppSettings:
    raw_loudness = _required(parser, "general", "music_loudness_lufs")
    try:
        loudness = float(raw_loudness.replace(",", "."))
    except ValueError as exc:
        raise SettingsError("Параметр general.music_loudness_lufs должен быть числом.") from exc
    if not -30.0 <= loudness <= -5.0:
        raise SettingsError(
            "Параметр general.music_loudness_lufs должен быть от -30 до -5 LUFS."
        )

    return AppSettings(
        general=GeneralSettings(
            hook_position=_enum(
                HookPosition, parser, "general", "hook_position"
            ),
            music_fragment=_enum(
                MusicFragment, parser, "general", "music_fragment"
            ),
            music_loudness_lufs=loudness,
        ),
        hook=_text_style(parser, "hook"),
        subhook=_text_style(parser, "subhook"),
        subhook_animation=_subhook_animation(parser),
    )


def load_settings(path: str | Path) -> AppSettings:
    path = Path(path)
    parser = configparser.ConfigParser(interpolation=None, inline_comment_prefixes=())
    try:
        with path.open("r", encoding="utf-8-sig") as handle:
            parser.read_file(handle)
    except FileNotFoundError as exc:
        raise SettingsError(f"Файл settings.ini не найден: {path}") from exc
    except (OSError, configparser.Error) as exc:
        raise SettingsError(f"Не удалось прочитать settings.ini: {exc}") from exc
    return _settings_from_parser(parser)


def default_settings() -> AppSettings:
    from .project import DEFAULT_SETTINGS_INI

    parser = configparser.ConfigParser(interpolation=None, inline_comment_prefixes=())
    try:
        parser.read_string(DEFAULT_SETTINGS_INI)
    except configparser.Error as exc:
        raise SettingsError(
            f"Встроенные стандартные настройки повреждены: {exc}"
        ) from exc
    return _settings_from_parser(parser)


def settings_to_ini(settings: AppSettings) -> str:
    def text_style(section: str, style: TextStyleSettings) -> str:
        extra = ""
        if section == "subhook":
            extra = (
                f"animation = {settings.subhook_animation.animation.value}\n"
                f"appear_at = {settings.subhook_animation.appear_at:g}\n"
            )
        return (
            f"[{section}]\n"
            f"font = {style.font}\n"
            f"font_size = {style.font_size}\n"
            f"text_color = {style.text_color.upper()}\n"
            f"outline_width = {style.outline_width}\n"
            f"outline_color = {style.outline_color.upper()}\n"
            f"background_style = {style.background_style.value}\n"
            f"background_color = {style.background_color.upper()}\n"
            f"background_opacity = {style.background_opacity}\n"
            f"background_padding = {style.background_padding}\n"
            f"background_corner_radius = {style.background_corner_radius}\n"
            f"glow_color = {style.glow_color.upper()}\n"
            f"glow_opacity = {style.glow_opacity}\n"
            f"glow_radius = {style.glow_radius}\n"
            f"{extra}"
        )

    return (
        "# Easy Reels Generator 0.8.0 — файл создан через окно настроек.\n"
        "# Обычному пользователю редактировать этот файл вручную не требуется.\n\n"
        "[general]\n"
        f"hook_position = {settings.general.hook_position.value}\n"
        f"music_fragment = {settings.general.music_fragment.value}\n"
        f"music_loudness_lufs = {settings.general.music_loudness_lufs:g}\n\n"
        f"{text_style('hook', settings.hook)}\n"
        f"{text_style('subhook', settings.subhook)}"
    )


def save_settings(path: str | Path, settings: AppSettings) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    contents = settings_to_ini(settings)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            prefix=".settings-",
            suffix=".tmp",
            dir=path.parent,
            delete=False,
        ) as handle:
            handle.write(contents)
            handle.flush()
            temporary_path = Path(handle.name)
        # Validate exactly what will be installed before replacing the live file.
        load_settings(temporary_path)
        temporary_path.replace(path)
    except (OSError, SettingsError) as exc:
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass
        if isinstance(exc, SettingsError):
            raise
        raise SettingsError(f"Не удалось сохранить settings.ini: {exc}") from exc
    return path
