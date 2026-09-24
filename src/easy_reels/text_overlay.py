from __future__ import annotations

import random
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .errors import TextLayoutError
from .models import (
    AppSettings,
    BackgroundStyle,
    HookPosition,
    TextOverlayLayers,
    TextStyleSettings,
)


FRAME_WIDTH = 1080
FRAME_HEIGHT = 1920
SAFE_LEFT = 90
SAFE_RIGHT = 990
SAFE_TOP = 285
SAFE_BOTTOM = 1500
SAFE_WIDTH = SAFE_RIGHT - SAFE_LEFT
SAFE_HEIGHT = SAFE_BOTTOM - SAFE_TOP
TOP_ANCHOR = 510
BOTTOM_ANCHOR = 1340
HOOK_MIN_SIZE = 48
SUBHOOK_MIN_SIZE = 32
HOOK_SUBHOOK_GAP = 28
AUTO_OUTLINE_WIDTH = 6
COMPACT_LINE_GAP_RATIO = 0.025
REGULAR_LINE_GAP_RATIO = 0.08
PAPER_LETTER_GAP_RATIO = 0.02


EMOJI_RANGES = (
    (0x1F000, 0x1FAFF),
    (0x2600, 0x27BF),
    (0x2300, 0x23FF),
    (0x1F1E6, 0x1F1FF),
    (0x1F3FB, 0x1F3FF),
)
SPACE_RE = re.compile(r"[ \t\f\v]+")
SPACE_BEFORE_PUNCTUATION_RE = re.compile(r"\s+([,.;:!?])")


def _is_emoji_codepoint(codepoint: int) -> bool:
    if codepoint in {0x200D, 0x20E3, 0xFE0E, 0xFE0F}:
        return True
    return any(start <= codepoint <= end for start, end in EMOJI_RANGES)


def remove_emojis(text: str) -> str:
    filtered = "".join(
        character for character in text if not _is_emoji_codepoint(ord(character))
    )
    lines = [
        SPACE_BEFORE_PUNCTUATION_RE.sub(
            r"\1", SPACE_RE.sub(" ", line).strip()
        )
        for line in filtered.splitlines()
    ]
    return "\n".join(lines).strip()


def hex_rgba(color: str, alpha: int = 255) -> tuple[int, int, int, int]:
    value = color.lstrip("#")
    return (
        int(value[0:2], 16),
        int(value[2:4], 16),
        int(value[4:6], 16),
        alpha,
    )


@dataclass(slots=True)
class TextLayout:
    text: str
    lines: list[str]
    font: ImageFont.FreeTypeFont
    font_size: int
    line_bboxes: list[tuple[int, int, int, int]]
    line_origins: list[tuple[int, int]]
    background_boxes: list[tuple[int, int, int, int] | None]
    width: int
    height: int
    stroke_width: int
    style: TextStyleSettings
    paper_glyphs: list["PaperGlyph"] | None = None


@dataclass(slots=True)
class PaperGlyph:
    text: str
    baseline_origin: tuple[int, int]
    tile_box: tuple[int, int, int, int]
    line_index: int


def _effective_stroke_width(style: TextStyleSettings) -> int:
    if (
        style.background_style == BackgroundStyle.OUTLINE
        and style.outline_width == 0
    ):
        return AUTO_OUTLINE_WIDTH
    return style.outline_width


def _outer_margin(style: TextStyleSettings) -> int:
    if style.background_style == BackgroundStyle.GLOW:
        # Два радиуса дают размытому свечению место и не обрезают его краями PNG.
        return max(style.background_padding, style.glow_radius * 2)
    return style.background_padding


def _text_width(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont,
    stroke_width: int,
) -> int:
    if not text:
        return 0
    box = draw.textbbox((0, 0), text, font=font, stroke_width=stroke_width)
    return box[2] - box[0]


def _wrap_words(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont,
    maximum_width: int,
    stroke_width: int,
) -> list[str] | None:
    result: list[str] = []
    for manual_line in text.split("\n"):
        if not manual_line:
            result.append("")
            continue
        words = manual_line.split()
        current = ""
        for word in words:
            if _text_width(draw, word, font, stroke_width) > maximum_width:
                return None
            candidate = word if not current else f"{current} {word}"
            if _text_width(draw, candidate, font, stroke_width) <= maximum_width:
                current = candidate
            else:
                result.append(current)
                current = word
        result.append(current)
    return result


def _measured_bbox(
    draw: ImageDraw.ImageDraw,
    line: str,
    font: ImageFont.FreeTypeFont,
    stroke_width: int,
) -> tuple[int, int, int, int]:
    measured = line or "Аg"
    box = draw.textbbox(
        (0, 0), measured, font=font, stroke_width=stroke_width
    )
    if line:
        return box
    # Пустая ручная строка сохраняет высоту, но не создаёт видимую ширину.
    return (0, box[1], 0, box[3])


def _line_gap(font_size: int, *, separate_backgrounds: bool) -> int:
    """Return a visually stable gap that scales with the rendered font."""
    ratio = (
        COMPACT_LINE_GAP_RATIO
        if separate_backgrounds
        else REGULAR_LINE_GAP_RATIO
    )
    return max(1 if separate_backgrounds else 3, round(font_size * ratio))


def _paper_units(text: str) -> list[str]:
    """Keep combining marks on the same paper tile as their base character."""
    units: list[str] = []
    for character in text:
        if unicodedata.combining(character) and units and not units[-1].isspace():
            units[-1] += character
        else:
            units.append(character)
    return units


def _paper_padding(style: TextStyleSettings) -> tuple[int, int]:
    # The regular padding value also controls paper letters, but is scaled down:
    # a full line background needs more air than a small tile around one glyph.
    if style.background_padding <= 0:
        return (0, 0)
    return (
        max(1, round(style.background_padding * 0.45)),
        max(1, round(style.background_padding * 0.35)),
    )


def _paper_glyph_bbox(
    draw: ImageDraw.ImageDraw,
    unit: str,
    font: ImageFont.FreeTypeFont,
    stroke_width: int,
) -> tuple[int, int, int, int]:
    return draw.textbbox(
        (0, 0),
        unit,
        font=font,
        stroke_width=stroke_width,
        anchor="ls",
    )


def _paper_line_measurements(
    draw: ImageDraw.ImageDraw,
    line: str,
    font: ImageFont.FreeTypeFont,
    stroke_width: int,
    style: TextStyleSettings,
) -> tuple[
    int,
    list[tuple[str, tuple[int, int, int, int], int]],
]:
    padding_x, padding_y = _paper_padding(style)
    overlap = max(1, round(font.size * 0.035))
    space_width = max(1, round(font.getlength(" ")))
    cursor = 0
    previous_was_glyph = False
    measurements: list[tuple[str, tuple[int, int, int, int], int]] = []
    for unit in _paper_units(line):
        if unit.isspace():
            cursor += space_width
            previous_was_glyph = False
            continue
        bbox = _paper_glyph_bbox(draw, unit, font, stroke_width)
        tile_width = max(1, bbox[2] - bbox[0]) + 2 * padding_x
        if previous_was_glyph:
            cursor -= min(overlap, max(0, tile_width // 4))
        measurements.append((unit, bbox, cursor))
        cursor += tile_width
        previous_was_glyph = True
    return cursor, measurements


def _paper_text_width(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont,
    stroke_width: int,
    style: TextStyleSettings,
) -> int:
    return _paper_line_measurements(
        draw, text, font, stroke_width, style
    )[0]


def _wrap_paper_words(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont,
    maximum_width: int,
    stroke_width: int,
    style: TextStyleSettings,
) -> list[str] | None:
    result: list[str] = []
    for manual_line in text.split("\n"):
        if not manual_line:
            result.append("")
            continue
        words = manual_line.split()
        current = ""
        for word in words:
            if (
                _paper_text_width(draw, word, font, stroke_width, style)
                > maximum_width
            ):
                return None
            candidate = word if not current else f"{current} {word}"
            if (
                _paper_text_width(draw, candidate, font, stroke_width, style)
                <= maximum_width
            ):
                current = candidate
            else:
                result.append(current)
                current = word
        result.append(current)
    return result


def _build_paper_layout(
    draw: ImageDraw.ImageDraw,
    text: str,
    lines: list[str],
    font: ImageFont.FreeTypeFont,
    font_size: int,
    stroke_width: int,
    style: TextStyleSettings,
) -> TextLayout:
    padding_x, padding_y = _paper_padding(style)
    variation_margin = max(8, round(font_size * 0.09))
    line_gap = max(1, round(font_size * PAPER_LETTER_GAP_RATIO / 2))
    measured_lines = [
        _paper_line_measurements(draw, line, font, stroke_width, style)
        for line in lines
    ]
    line_widths = [item[0] for item in measured_lines]
    line_extents: list[tuple[int, int]] = []
    for line, (_, glyphs) in zip(lines, measured_lines):
        if line and glyphs:
            line_extents.append(
                (
                    min(bbox[1] - padding_y for _, bbox, _ in glyphs),
                    max(bbox[3] + padding_y for _, bbox, _ in glyphs),
                )
            )
        else:
            ascent, descent = font.getmetrics()
            line_extents.append((-ascent - padding_y, descent + padding_y))

    row_heights = [
        max(1, bottom - top) + 2 * variation_margin
        for top, bottom in line_extents
    ]
    width = max(line_widths, default=1) + 2 * variation_margin
    height = sum(row_heights) + max(0, len(lines) - 1) * line_gap
    glyph_layouts: list[PaperGlyph] = []
    cursor_y = 0
    for line_index, ((line_width, glyphs), (line_top, _), row_height) in enumerate(
        zip(measured_lines, line_extents, row_heights)
    ):
        line_left = variation_margin + (max(line_widths, default=1) - line_width) // 2
        baseline_y = cursor_y + variation_margin - line_top
        for unit, bbox, offset_x in glyphs:
            tile_left = line_left + offset_x
            tile_top = baseline_y + bbox[1] - padding_y
            tile_right = tile_left + max(1, bbox[2] - bbox[0]) + 2 * padding_x
            tile_bottom = baseline_y + bbox[3] + padding_y
            baseline_x = tile_left + padding_x - bbox[0]
            glyph_layouts.append(
                PaperGlyph(
                    text=unit,
                    baseline_origin=(baseline_x, baseline_y),
                    tile_box=(tile_left, tile_top, tile_right, tile_bottom),
                    line_index=line_index,
                )
            )
        cursor_y += row_height + line_gap

    return TextLayout(
        text=text,
        lines=lines,
        font=font,
        font_size=font_size,
        line_bboxes=[],
        line_origins=[],
        background_boxes=[],
        width=max(1, width),
        height=max(1, height),
        stroke_width=stroke_width,
        style=style,
        paper_glyphs=glyph_layouts,
    )


def _build_layout(
    draw: ImageDraw.ImageDraw,
    text: str,
    lines: list[str],
    font: ImageFont.FreeTypeFont,
    font_size: int,
    stroke_width: int,
    style: TextStyleSettings,
) -> TextLayout:
    bboxes = [
        _measured_bbox(draw, line, font, stroke_width) for line in lines
    ]
    widths = [box[2] - box[0] for box in bboxes]
    heights = [max(1, box[3] - box[1]) for box in bboxes]
    separate_backgrounds = style.background_style in {
        BackgroundStyle.LINES,
        BackgroundStyle.TORN_PAPER,
    }
    line_gap = _line_gap(
        font_size,
        separate_backgrounds=separate_backgrounds,
    )
    # Одинаковая оптическая высота всех строк делает блок ровным даже тогда,
    # когда в одной строке есть выносные элементы букв, а в другой их нет.
    common_glyph_height = max(heights, default=1)

    origins: list[tuple[int, int]] = []
    background_boxes: list[tuple[int, int, int, int] | None] = []
    if separate_backgrounds:
        padding = style.background_padding
        torn_margin = 10 if style.background_style == BackgroundStyle.TORN_PAPER else 0
        row_heights = [common_glyph_height + 2 * padding for _ in heights]
        row_widths = [width + 2 * padding for width in widths]
        width = max(row_widths, default=1) + 2 * torn_margin
        height = (
            sum(row_heights)
            + max(0, len(lines) - 1) * line_gap
            + 2 * torn_margin
        )
        cursor_y = torn_margin
        for line, box, glyph_width, glyph_height, row_width, row_height in zip(
            lines, bboxes, widths, heights, row_widths, row_heights
        ):
            row_left = (width - row_width) // 2
            glyph_left = (width - glyph_width) // 2
            glyph_top = (
                cursor_y
                + padding
                + (common_glyph_height - glyph_height) // 2
            )
            origins.append((glyph_left - box[0], glyph_top - box[1]))
            background_boxes.append(
                (row_left, cursor_y, row_left + row_width, cursor_y + row_height)
                if line
                else None
            )
            cursor_y += row_height + line_gap
    else:
        margin = _outer_margin(style)
        content_width = max(widths, default=1)
        content_height = (
            len(lines) * common_glyph_height
            + max(0, len(lines) - 1) * line_gap
        )
        width = content_width + 2 * margin
        height = content_height + 2 * margin
        cursor_y = margin
        for box, glyph_width, glyph_height in zip(bboxes, widths, heights):
            glyph_left = (width - glyph_width) // 2
            glyph_top = cursor_y + (common_glyph_height - glyph_height) // 2
            origins.append((glyph_left - box[0], glyph_top - box[1]))
            background_boxes.append(None)
            cursor_y += common_glyph_height + line_gap

    return TextLayout(
        text=text,
        lines=lines,
        font=font,
        font_size=font_size,
        line_bboxes=bboxes,
        line_origins=origins,
        background_boxes=background_boxes,
        width=max(1, width),
        height=max(1, height),
        stroke_width=stroke_width,
        style=style,
    )


def _fit_layout(
    text: str,
    style: TextStyleSettings,
    font_path: Path,
    minimum_size: int,
    maximum_height: int,
) -> TextLayout:
    cleaned = remove_emojis(text)
    if not cleaned:
        raise TextLayoutError("После удаления эмодзи текст оказался пустым.")
    if not font_path.is_file():
        raise TextLayoutError(f"Шрифт не найден: {font_path.name}")

    scratch = Image.new("RGBA", (FRAME_WIDTH, FRAME_HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(scratch)
    stroke_width = _effective_stroke_width(style)
    if style.background_style == BackgroundStyle.PAPER_LETTERS:
        horizontal_margin = max(4, round(style.font_size * 0.07))
    elif style.background_style in {
        BackgroundStyle.LINES,
        BackgroundStyle.TORN_PAPER,
    }:
        horizontal_margin = style.background_padding
        if style.background_style == BackgroundStyle.TORN_PAPER:
            horizontal_margin += 10
    else:
        horizontal_margin = _outer_margin(style)
    usable_width = SAFE_WIDTH - 2 * horizontal_margin
    if usable_width <= 0:
        raise TextLayoutError("Отступы и обводка оставляют тексту нулевую ширину.")

    lowest_size = min(style.font_size, minimum_size)
    sizes = list(range(style.font_size, lowest_size - 1, -2))
    if lowest_size not in sizes:
        sizes.append(lowest_size)
    for size in sizes:
        try:
            font = ImageFont.truetype(str(font_path), size=size)
        except OSError as exc:
            raise TextLayoutError(f"Не удалось открыть шрифт «{font_path.name}».") from exc
        if style.background_style == BackgroundStyle.PAPER_LETTERS:
            lines = _wrap_paper_words(
                draw,
                cleaned,
                font,
                usable_width,
                stroke_width,
                style,
            )
        else:
            lines = _wrap_words(
                draw, cleaned, font, usable_width, stroke_width
            )
        if lines is None:
            continue
        if style.background_style == BackgroundStyle.PAPER_LETTERS:
            layout = _build_paper_layout(
                draw, cleaned, lines, font, size, stroke_width, style
            )
        else:
            layout = _build_layout(
                draw, cleaned, lines, font, size, stroke_width, style
            )
        if layout.width <= SAFE_WIDTH and layout.height <= maximum_height:
            return layout
    raise TextLayoutError(
        f"Текст не помещается в безопасную область даже при размере {minimum_size} px."
    )


def _rounded_rectangle(
    draw: ImageDraw.ImageDraw,
    bounds: tuple[int, int, int, int],
    radius: int,
    fill: tuple[int, int, int, int],
) -> None:
    draw.rounded_rectangle(bounds, radius=max(0, radius), fill=fill)


def _torn_polygon(
    left: int,
    top: int,
    right: int,
    bottom: int,
    rng: random.Random,
) -> list[tuple[int, int]]:
    step = max(12, (right - left) // 10)
    # Край рвётся только внутрь своей полосы. Поэтому соседние полупрозрачные
    # подложки могут стоять почти вплотную, но никогда не наслаиваются.
    jitter = max(1, min(3, (bottom - top) // 20))
    top_edge = [
        (x, top + rng.randint(0, jitter))
        for x in range(left, right, step)
    ]
    top_edge.append((right, top + rng.randint(0, jitter)))
    bottom_edge = [
        (x, bottom - rng.randint(0, jitter))
        for x in range(right, left, -step)
    ]
    bottom_edge.append((left, bottom - rng.randint(0, jitter)))
    return top_edge + bottom_edge


def _draw_background(
    draw: ImageDraw.ImageDraw,
    layout: TextLayout,
    rng: random.Random,
) -> None:
    style = layout.style
    if style.background_style in {
        BackgroundStyle.NONE,
        BackgroundStyle.OUTLINE,
        BackgroundStyle.GLOW,
        BackgroundStyle.PAPER_LETTERS,
    }:
        return
    fill = hex_rgba(
        style.background_color,
        round(255 * style.background_opacity / 100),
    )
    if style.background_style == BackgroundStyle.RECTANGLE:
        _rounded_rectangle(
            draw,
            (0, 0, layout.width - 1, layout.height - 1),
            style.background_corner_radius,
            fill,
        )
    elif style.background_style == BackgroundStyle.LINES:
        for box in layout.background_boxes:
            if box is None:
                continue
            left, top, right, bottom = box
            _rounded_rectangle(
                draw,
                (left, top, right - 1, bottom - 1),
                style.background_corner_radius,
                fill,
            )
    elif style.background_style == BackgroundStyle.TORN_PAPER:
        for box in layout.background_boxes:
            if box is None:
                continue
            left, top, right, bottom = box
            polygon = _torn_polygon(
                left,
                top,
                right - 1,
                bottom - 1,
                rng,
            )
            draw.polygon(polygon, fill=fill)


def _paper_tile_polygon(
    width: int,
    height: int,
    rng: random.Random,
    inset: int,
) -> list[tuple[int, int]]:
    left = inset
    top = inset
    right = inset + width - 1
    bottom = inset + height - 1
    jitter = max(1, min(3, round(min(width, height) * 0.045)))
    step_x = max(6, width // 4)
    step_y = max(6, height // 3)
    points: list[tuple[int, int]] = []
    for x in range(left, right, step_x):
        points.append((x, top + rng.randint(0, jitter)))
    points.append((right, top + rng.randint(0, jitter)))
    for y in range(top + step_y, bottom, step_y):
        points.append((right - rng.randint(0, jitter), y))
    points.append((right, bottom - rng.randint(0, jitter)))
    for x in range(right - step_x, left, -step_x):
        points.append((x, bottom - rng.randint(0, jitter)))
    points.append((left, bottom - rng.randint(0, jitter)))
    for y in range(bottom - step_y, top, -step_y):
        points.append((left + rng.randint(0, jitter), y))
    return points


def _render_paper_letters(
    layout: TextLayout,
    rng: random.Random,
) -> Image.Image:
    image = Image.new("RGBA", (layout.width, layout.height), (0, 0, 0, 0))
    style = layout.style
    paper_fill = hex_rgba(
        style.background_color,
        round(255 * style.background_opacity / 100),
    )
    text_fill = hex_rgba(style.text_color)
    outline_fill = hex_rgba(style.outline_color)
    variation = max(1, round(layout.font_size * 0.018))
    rotation_margin = max(4, round(layout.font_size * 0.09))

    for glyph in layout.paper_glyphs or ():
        left, top, right, bottom = glyph.tile_box
        tile_width = max(1, right - left)
        tile_height = max(1, bottom - top)
        patch = Image.new(
            "RGBA",
            (
                tile_width + 2 * rotation_margin,
                tile_height + 2 * rotation_margin,
            ),
            (0, 0, 0, 0),
        )
        patch_draw = ImageDraw.Draw(patch)
        polygon = _paper_tile_polygon(
            tile_width,
            tile_height,
            rng,
            rotation_margin,
        )
        patch_draw.polygon(polygon, fill=paper_fill)

        baseline_x = (
            glyph.baseline_origin[0] - left + rotation_margin
        )
        baseline_y = (
            glyph.baseline_origin[1] - top + rotation_margin
        )
        patch_draw.text(
            (baseline_x, baseline_y),
            glyph.text,
            font=layout.font,
            fill=text_fill,
            stroke_width=layout.stroke_width,
            stroke_fill=outline_fill,
            anchor="ls",
        )

        angle = rng.uniform(-2.4, 2.4)
        rotated = patch.rotate(
            angle,
            resample=Image.Resampling.BICUBIC,
            expand=True,
        )
        center_x = (left + right) // 2 + rng.randint(-variation, variation)
        center_y = (top + bottom) // 2 + rng.randint(-variation, variation)
        paste_x = round(center_x - rotated.width / 2)
        paste_y = round(center_y - rotated.height / 2)
        image.alpha_composite(rotated, (paste_x, paste_y))
    return image


def _render_block(layout: TextLayout, rng: random.Random) -> Image.Image:
    if layout.style.background_style == BackgroundStyle.PAPER_LETTERS:
        return _render_paper_letters(layout, rng)

    image = Image.new("RGBA", (layout.width, layout.height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    _draw_background(draw, layout, rng)
    style = layout.style
    text_fill = hex_rgba(style.text_color)
    outline_fill = hex_rgba(style.outline_color)

    if style.background_style == BackgroundStyle.GLOW:
        glow = Image.new("RGBA", image.size, (0, 0, 0, 0))
        glow_draw = ImageDraw.Draw(glow)
        glow_fill = hex_rgba(
            style.glow_color,
            round(255 * style.glow_opacity / 100),
        )
        glow_stroke = max(1, round(style.glow_radius * 0.22))
        for line, origin in zip(layout.lines, layout.line_origins):
            if line:
                glow_draw.text(
                    origin,
                    line,
                    font=layout.font,
                    fill=glow_fill,
                    stroke_width=glow_stroke,
                    stroke_fill=glow_fill,
                )
        wide_glow = glow.filter(ImageFilter.GaussianBlur(style.glow_radius))
        near_glow = glow.filter(
            ImageFilter.GaussianBlur(max(1, round(style.glow_radius / 3)))
        )
        image.alpha_composite(wide_glow)
        image.alpha_composite(near_glow)

    draw = ImageDraw.Draw(image)
    for line, origin in zip(layout.lines, layout.line_origins):
        if line:
            draw.text(
                origin,
                line,
                font=layout.font,
                fill=text_fill,
                stroke_width=layout.stroke_width,
                stroke_fill=outline_fill,
            )
    return image


def render_text_overlay(
    hook: str,
    subhook: str,
    settings: AppSettings,
    fonts_dir: str | Path,
    output_path: str | Path,
    *,
    seed: int,
    subhook_output_path: str | Path | None = None,
) -> TextOverlayLayers:
    fonts_dir = Path(fonts_dir)
    output_path = Path(output_path)
    subhook_output = Path(subhook_output_path) if subhook_output_path else None
    has_subhook = bool(remove_emojis(subhook))
    if has_subhook:
        hook_max_height = round((SAFE_HEIGHT - HOOK_SUBHOOK_GAP) * 0.58)
        subhook_max_height = SAFE_HEIGHT - HOOK_SUBHOOK_GAP - hook_max_height
    else:
        hook_max_height = SAFE_HEIGHT
        subhook_max_height = 0

    hook_layout = _fit_layout(
        hook,
        settings.hook,
        fonts_dir / settings.hook.font,
        HOOK_MIN_SIZE,
        hook_max_height,
    )
    subhook_layout = None
    if has_subhook:
        subhook_layout = _fit_layout(
            subhook,
            settings.subhook,
            fonts_dir / settings.subhook.font,
            SUBHOOK_MIN_SIZE,
            subhook_max_height,
        )

    rng = random.Random(seed)
    hook_image = _render_block(hook_layout, rng)
    subhook_image = _render_block(subhook_layout, rng) if subhook_layout else None
    total_height = hook_image.height
    if subhook_image:
        total_height += HOOK_SUBHOOK_GAP + subhook_image.height

    position = settings.general.hook_position
    anchor = TOP_ANCHOR if position == HookPosition.TOP else BOTTOM_ANCHOR
    top = round(anchor - total_height / 2)
    top = min(max(top, SAFE_TOP), SAFE_BOTTOM - total_height)

    overlay = Image.new("RGBA", (FRAME_WIDTH, FRAME_HEIGHT), (0, 0, 0, 0))
    x = (FRAME_WIDTH - hook_image.width) // 2
    overlay.alpha_composite(hook_image, (x, top))
    subhook_top = 0
    subhook_x = 0
    if subhook_image:
        subhook_top = top + hook_image.height + HOOK_SUBHOOK_GAP
        subhook_x = (FRAME_WIDTH - subhook_image.width) // 2
        if subhook_output is None:
            overlay.alpha_composite(subhook_image, (subhook_x, subhook_top))
        else:
            subhook_output.parent.mkdir(parents=True, exist_ok=True)
            subhook_image.save(subhook_output, format="PNG")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    overlay.save(output_path, format="PNG")
    return TextOverlayLayers(
        hook_path=output_path,
        subhook_path=subhook_output if subhook_image and subhook_output else None,
        subhook_x=subhook_x,
        subhook_y=subhook_top,
        subhook_width=subhook_image.width if subhook_image else 0,
        subhook_height=subhook_image.height if subhook_image else 0,
    )
