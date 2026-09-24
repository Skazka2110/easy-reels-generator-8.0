from __future__ import annotations

import shutil
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontDatabase
from PySide6.QtWidgets import (
    QComboBox,
    QColorDialog,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..config import COLOR_RE, default_settings, load_settings, save_settings
from ..errors import SettingsError
from ..models import (
    AppSettings,
    BackgroundStyle,
    GeneralSettings,
    HookPosition,
    MusicFragment,
    SubhookAnimation,
    SubhookAnimationSettings,
    TextStyleSettings,
)
from .theme import ACCENT, ERROR


BACKGROUND_STYLES = (
    ("Классический прямоугольник", BackgroundStyle.RECTANGLE),
    ("Подложка под каждой строкой", BackgroundStyle.LINES),
    ("Рваная бумага под строками", BackgroundStyle.TORN_PAPER),
    ("Отдельная бумажка под каждой буквой", BackgroundStyle.PAPER_LETTERS),
    ("Обводка вокруг букв", BackgroundStyle.OUTLINE),
    ("Свечение вокруг букв", BackgroundStyle.GLOW),
    ("Без подложки", BackgroundStyle.NONE),
)

STYLE_PRESETS: tuple[tuple[str, dict[str, object] | None], ...] = (
    ("Свои текущие настройки", None),
    (
        "Классика: белый текст на тёмном",
        {
            "background_style": BackgroundStyle.RECTANGLE,
            "text_color": "#FFFFFF",
            "background_color": "#111111",
            "background_opacity": 90,
            "background_padding": 18,
            "background_corner_radius": 12,
            "outline_width": 0,
        },
    ),
    (
        "По строкам: белый текст на тёмном",
        {
            "background_style": BackgroundStyle.LINES,
            "text_color": "#FFFFFF",
            "background_color": "#111111",
            "background_opacity": 92,
            "background_padding": 14,
            "background_corner_radius": 8,
            "outline_width": 0,
        },
    ),
    (
        "Рваная бумага: чёрный текст",
        {
            "background_style": BackgroundStyle.TORN_PAPER,
            "text_color": "#111111",
            "background_color": "#FFFFFF",
            "background_opacity": 92,
            "background_padding": 16,
            "outline_width": 0,
        },
    ),
    (
        "Бумажные буквы: чёрный текст",
        {
            "background_style": BackgroundStyle.PAPER_LETTERS,
            "text_color": "#111111",
            "background_color": "#FFFFFF",
            "background_opacity": 96,
            "background_padding": 16,
            "outline_width": 0,
        },
    ),
    (
        "Обводка: белые буквы",
        {
            "background_style": BackgroundStyle.OUTLINE,
            "text_color": "#FFFFFF",
            "outline_color": "#000000",
            "outline_width": 6,
        },
    ),
    (
        "Неоновое свечение",
        {
            "background_style": BackgroundStyle.GLOW,
            "text_color": "#FFFFFF",
            "outline_width": 0,
            "glow_color": "#39FF88",
            "glow_opacity": 80,
            "glow_radius": 18,
        },
    ),
    (
        "Только текст",
        {
            "background_style": BackgroundStyle.NONE,
            "text_color": "#FFFFFF",
            "outline_width": 0,
        },
    ),
)


def _row(label_text: str, control: QWidget, hint: str = "") -> QWidget:
    widget = QWidget()
    layout = QGridLayout(widget)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setHorizontalSpacing(14)
    layout.setVerticalSpacing(3)
    label = QLabel(label_text)
    label.setMinimumWidth(205)
    layout.addWidget(label, 0, 0)
    layout.addWidget(control, 0, 1)
    layout.setColumnStretch(1, 1)
    if hint:
        help_label = QLabel(hint)
        help_label.setObjectName("SettingsHint")
        help_label.setWordWrap(True)
        layout.addWidget(help_label, 1, 1)
    return widget


class ColorField(QWidget):
    changed = Signal(str)

    def __init__(self, value: str, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self.input = QLineEdit()
        self.input.setMaxLength(7)
        self.input.setPlaceholderText("#RRGGBB")
        self.input.setMinimumWidth(125)
        self.button = QPushButton("Выбрать цвет")
        self.button.setMinimumWidth(145)
        layout.addWidget(self.input, 1)
        layout.addWidget(self.button)
        self.input.editingFinished.connect(self._finish_editing)
        self.button.clicked.connect(self._choose_color)
        self.set_value(value)

    def set_value(self, value: str) -> None:
        value = value.strip().upper()
        self.input.setText(value)
        self._update_button(value)
        self.changed.emit(value)

    def value(self) -> str:
        value = self.input.text().strip().upper()
        if not COLOR_RE.fullmatch(value):
            raise SettingsError(
                f"Цвет «{self.input.text()}» должен иметь формат #RRGGBB."
            )
        return value

    def _finish_editing(self) -> None:
        value = self.input.text().strip().upper()
        if COLOR_RE.fullmatch(value):
            self.input.setText(value)
            self._update_button(value)
            self.input.setStyleSheet("")
            self.changed.emit(value)
        else:
            self.input.setStyleSheet(f"border-color: {ERROR};")

    def _choose_color(self) -> None:
        initial = QColor(self.input.text())
        if not initial.isValid():
            initial = QColor("#FFFFFF")
        color = QColorDialog.getColor(initial, self, "Выберите точный цвет")
        if color.isValid():
            self.set_value(color.name().upper())
            self.input.setStyleSheet("")

    def _update_button(self, value: str) -> None:
        color = QColor(value)
        if not color.isValid():
            self.button.setStyleSheet("")
            return
        lightness = color.lightness()
        foreground = "#050806" if lightness > 150 else "#FFFFFF"
        self.button.setStyleSheet(
            f"background-color: {value}; color: {foreground}; "
            f"border: 1px solid {value};"
        )


class SliderSpin(QWidget):
    value_changed = Signal(float)

    def __init__(
        self,
        minimum: float,
        maximum: float,
        *,
        decimals: int = 0,
        step: float = 1,
        suffix: str = "",
        parent=None,
    ):
        super().__init__(parent)
        self.decimals = decimals
        self.factor = 10**decimals
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(
            round(minimum * self.factor),
            round(maximum * self.factor),
        )
        self.slider.setSingleStep(max(1, round(step * self.factor)))
        if decimals:
            spin = QDoubleSpinBox()
            spin.setDecimals(decimals)
            spin.setSingleStep(step)
            spin.setRange(float(minimum), float(maximum))
        else:
            spin = QSpinBox()
            spin.setSingleStep(round(step))
            spin.setRange(round(minimum), round(maximum))
        spin.setSuffix(suffix)
        spin.setMinimumWidth(105)
        self.spin = spin
        layout.addWidget(self.slider, 1)
        layout.addWidget(self.spin)
        self.slider.valueChanged.connect(self._from_slider)
        self.spin.valueChanged.connect(self._from_spin)

    def set_value(self, value: float) -> None:
        self.slider.blockSignals(True)
        self.spin.blockSignals(True)
        self.slider.setValue(round(value * self.factor))
        self.spin.setValue(value)
        self.slider.blockSignals(False)
        self.spin.blockSignals(False)
        self.value_changed.emit(float(value))

    def value(self) -> int | float:
        value = self.spin.value()
        return float(value) if self.decimals else int(value)

    def _from_slider(self, value: int) -> None:
        result = value / self.factor
        self.spin.blockSignals(True)
        self.spin.setValue(result)
        self.spin.blockSignals(False)
        self.value_changed.emit(float(result))

    def _from_spin(self, value: float) -> None:
        self.slider.blockSignals(True)
        self.slider.setValue(round(float(value) * self.factor))
        self.slider.blockSignals(False)
        self.value_changed.emit(float(value))


class CollapsibleSection(QWidget):
    def __init__(self, title: str, *, expanded: bool = False, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self.toggle = QPushButton()
        self.toggle.setObjectName("CollapseButton")
        self.toggle.setCheckable(True)
        self.toggle.setChecked(expanded)
        self.content = QFrame()
        self.content.setObjectName("SettingsPanel")
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(16, 15, 16, 15)
        self.content_layout.setSpacing(12)
        layout.addWidget(self.toggle)
        layout.addWidget(self.content)
        self._title = title
        self.toggle.toggled.connect(self._set_expanded)
        self._set_expanded(expanded)

    def _set_expanded(self, expanded: bool) -> None:
        self.content.setVisible(expanded)
        arrow = "▾" if expanded else "▸"
        self.toggle.setText(f"{arrow}  {self._title}")


class FontSelector(QWidget):
    changed = Signal(str)
    font_added = Signal(str)

    def __init__(self, fonts_dir: Path, parent=None):
        super().__init__(parent)
        self.fonts_dir = fonts_dir
        self.fonts_dir.mkdir(parents=True, exist_ok=True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        chooser = QHBoxLayout()
        self.combo = QComboBox()
        self.combo.setEditable(True)
        self.combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.combo.setMinimumWidth(280)
        self.add_button = QPushButton("Добавить свой шрифт")
        chooser.addWidget(self.combo, 1)
        chooser.addWidget(self.add_button)
        layout.addLayout(chooser)
        self.sample = QLabel("Пример: Ваш яркий хук")
        self.sample.setObjectName("FontSample")
        self.sample.setMinimumHeight(58)
        self.sample.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.sample)
        self.error = QLabel("")
        self.error.setObjectName("ValidationError")
        self.error.setWordWrap(True)
        self.error.hide()
        layout.addWidget(self.error)
        self.combo.currentTextChanged.connect(self._update_preview)
        self.add_button.clicked.connect(self._add_font)
        self.refresh()

    def refresh(self, selected: str | None = None) -> None:
        selected = selected if selected is not None else self.combo.currentText()
        names = sorted(
            (
                path.name
                for path in self.fonts_dir.iterdir()
                if path.is_file() and path.suffix.lower() in {".ttf", ".otf"}
            ),
            key=str.casefold,
        )
        self.combo.blockSignals(True)
        self.combo.clear()
        self.combo.addItems(names)
        self.combo.setCurrentText(selected or (names[0] if names else ""))
        self.combo.blockSignals(False)
        self._update_preview(self.combo.currentText())

    def set_value(self, font_name: str) -> None:
        self.refresh(font_name)

    def value(self) -> str:
        name = self.combo.currentText().strip()
        path = Path(name)
        if (
            not name
            or path.name != name
            or path.suffix.lower() not in {".ttf", ".otf"}
        ):
            raise SettingsError(
                "Укажите точное имя файла шрифта с расширением .ttf или .otf."
            )
        font_path = self.fonts_dir / name
        if not font_path.is_file():
            raise SettingsError(
                f"Шрифт «{name}» не найден в папке fonts."
            )
        font_id = QFontDatabase.addApplicationFont(str(font_path))
        if font_id < 0:
            raise SettingsError(
                f"Файл шрифта «{name}» повреждён или не поддерживается."
            )
        return name

    def _update_preview(self, name: str) -> None:
        name = name.strip()
        font_path = self.fonts_dir / name
        if not font_path.is_file():
            self.error.setText(
                "Такого файла пока нет в папке fonts. "
                "Выберите шрифт из списка или добавьте свой."
            )
            self.error.show()
            self.sample.setFont(QFont())
            self.changed.emit(name)
            return
        font_id = QFontDatabase.addApplicationFont(str(font_path))
        families = (
            QFontDatabase.applicationFontFamilies(font_id)
            if font_id >= 0
            else []
        )
        if not families:
            self.error.setText(
                "Не удалось прочитать этот шрифт. Выберите другой файл."
            )
            self.error.show()
            self.sample.setFont(QFont())
        else:
            sample_font = QFont(families[0])
            sample_font.setPixelSize(27)
            self.sample.setFont(sample_font)
            self.error.hide()
        self.changed.emit(name)

    def _add_font(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Добавить свой шрифт",
            "",
            "Шрифты (*.ttf *.otf)",
        )
        if not filename:
            return
        source = Path(filename)
        destination = self.fonts_dir / source.name
        try:
            if source.resolve() != destination.resolve():
                counter = 2
                while destination.exists():
                    destination = (
                        self.fonts_dir
                        / f"{source.stem}_{counter}{source.suffix.lower()}"
                    )
                    counter += 1
                shutil.copy2(source, destination)
        except OSError as exc:
            QMessageBox.critical(
                self,
                "Не удалось добавить шрифт",
                f"Файл не удалось скопировать в папку fonts:\n{exc}",
            )
            return
        self.refresh(destination.name)
        self.font_added.emit(destination.name)


class GeneralSettingsEditor(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 8, 4, 8)
        layout.setSpacing(16)

        intro = QLabel(
            "Здесь выбирается расположение текста и поведение музыки. "
            "Программа сама возьмёт видео из папки videos/top или videos/bottom."
        )
        intro.setObjectName("SettingsHint")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        panel = QFrame()
        panel.setObjectName("SettingsPanel")
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(18, 17, 18, 17)
        panel_layout.setSpacing(14)

        self.position = QComboBox()
        self.position.addItem(
            "Сверху — видео из videos/top", HookPosition.TOP.value
        )
        self.position.addItem(
            "Снизу — видео из videos/bottom", HookPosition.BOTTOM.value
        )
        panel_layout.addWidget(
            _row(
                "Положение текста",
                self.position,
                "Хук и подхук перемещаются вместе.",
            )
        )

        self.music_fragment = QComboBox()
        self.music_fragment.addItem(
            "С начала каждого трека", MusicFragment.START.value
        )
        self.music_fragment.addItem(
            "Со случайного места", MusicFragment.RANDOM.value
        )
        panel_layout.addWidget(
            _row(
                "Фрагмент музыки",
                self.music_fragment,
                "Если папка music пустая, ролики останутся без музыки.",
            )
        )

        self.loudness_preset = QComboBox()
        self.loudness_preset.addItem("Тише (−18 LUFS)", -18.0)
        self.loudness_preset.addItem("Стандартно (−14 LUFS)", -14.0)
        self.loudness_preset.addItem("Громче (−10 LUFS)", -10.0)
        self.loudness_preset.addItem("Своё точное значение", None)
        panel_layout.addWidget(
            _row("Готовая громкость", self.loudness_preset)
        )
        self.loudness = SliderSpin(
            -30,
            -5,
            decimals=1,
            step=0.5,
            suffix=" LUFS",
        )
        panel_layout.addWidget(
            _row(
                "Точная громкость",
                self.loudness,
                "Допустимо от −30 до −5 LUFS. Чем ближе к нулю, тем громче.",
            )
        )
        self.loudness_preset.currentIndexChanged.connect(
            self._apply_loudness_preset
        )
        self.loudness.value_changed.connect(self._match_loudness_preset)
        layout.addWidget(panel)
        layout.addStretch(1)

    def load(self, settings: GeneralSettings) -> None:
        self._set_combo_data(self.position, settings.hook_position)
        self._set_combo_data(self.music_fragment, settings.music_fragment)
        self.loudness.set_value(settings.music_loudness_lufs)
        self._match_loudness_preset(settings.music_loudness_lufs)

    def settings(self) -> GeneralSettings:
        return GeneralSettings(
            hook_position=HookPosition(self.position.currentData()),
            music_fragment=MusicFragment(self.music_fragment.currentData()),
            music_loudness_lufs=float(self.loudness.value()),
        )

    @staticmethod
    def _set_combo_data(combo: QComboBox, value) -> None:
        index = combo.findData(getattr(value, "value", value))
        if index >= 0:
            combo.setCurrentIndex(index)

    def _apply_loudness_preset(self, _index: int = -1) -> None:
        value = self.loudness_preset.currentData()
        if value is not None:
            self.loudness.set_value(float(value))

    def _match_loudness_preset(self, value: float) -> None:
        matching = next(
            (
                index
                for index in range(self.loudness_preset.count() - 1)
                if float(self.loudness_preset.itemData(index)) == float(value)
            ),
            self.loudness_preset.count() - 1,
        )
        self.loudness_preset.blockSignals(True)
        self.loudness_preset.setCurrentIndex(matching)
        self.loudness_preset.blockSignals(False)


class TextStyleEditor(QWidget):
    def __init__(
        self,
        fonts_dir: Path,
        *,
        role_name: str,
        include_animation: bool = False,
        parent=None,
    ):
        super().__init__(parent)
        self.include_animation = include_animation
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 8, 4, 8)
        layout.setSpacing(14)

        intro = QLabel(
            f"Настройки блока «{role_name}». Сначала можно выбрать готовый стиль, "
            "а затем при желании изменить любое точное значение."
        )
        intro.setObjectName("SettingsHint")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        basic = QFrame()
        basic.setObjectName("SettingsPanel")
        basic_layout = QVBoxLayout(basic)
        basic_layout.setContentsMargins(18, 17, 18, 17)
        basic_layout.setSpacing(13)

        self.preset = QComboBox()
        for name, _values in STYLE_PRESETS:
            self.preset.addItem(name)
        basic_layout.addWidget(
            _row(
                "Готовый стиль",
                self.preset,
                "Готовый вариант можно использовать сразу или донастроить ниже.",
            )
        )

        self.font = FontSelector(fonts_dir)
        basic_layout.addWidget(
            _row(
                "Шрифт",
                self.font,
                "Список автоматически читает все .ttf и .otf из папки fonts.",
            )
        )
        self.font_size = SliderSpin(1, 400, suffix=" px")
        basic_layout.addWidget(
            _row(
                "Размер шрифта",
                self.font_size,
                "Если длинный текст не помещается, программа уменьшит его автоматически.",
            )
        )
        self.text_color = ColorField("#FFFFFF")
        basic_layout.addWidget(_row("Цвет текста", self.text_color))
        self.background_style = QComboBox()
        for label, value in BACKGROUND_STYLES:
            self.background_style.addItem(label, value.value)
        basic_layout.addWidget(
            _row(
                "Подложка или эффект",
                self.background_style,
                "«Бумажные буквы» создают отдельную бумажку под каждым символом.",
            )
        )
        layout.addWidget(basic)

        self.background_group = QGroupBox("Подложка")
        background_layout = QVBoxLayout(self.background_group)
        background_layout.setSpacing(12)
        self.background_color = ColorField("#FFFFFF")
        self.background_opacity = SliderSpin(0, 100, suffix=" %")
        self.background_padding = SliderSpin(0, 200, suffix=" px")
        self.background_corner_radius = SliderSpin(0, 200, suffix=" px")
        background_layout.addWidget(_row("Цвет подложки", self.background_color))
        background_layout.addWidget(
            _row(
                "Прозрачность",
                self.background_opacity,
                "0% — подложка невидимая, 100% — полностью непрозрачная.",
            )
        )
        background_layout.addWidget(
            _row("Отступ вокруг текста", self.background_padding)
        )
        self.corner_row = _row(
            "Скругление углов", self.background_corner_radius
        )
        background_layout.addWidget(self.corner_row)
        layout.addWidget(self.background_group)

        advanced = CollapsibleSection("Точные настройки обводки и свечения")
        self.outline_width = SliderSpin(0, 30, suffix=" px")
        self.outline_color = ColorField("#000000")
        self.glow_color = ColorField("#39FF88")
        self.glow_opacity = SliderSpin(0, 100, suffix=" %")
        self.glow_radius = SliderSpin(1, 100, suffix=" px")
        advanced.content_layout.addWidget(
            _row(
                "Толщина обводки",
                self.outline_width,
                "В режиме «Обводка» значение 0 включает автоматические 6 px.",
            )
        )
        advanced.content_layout.addWidget(
            _row("Цвет обводки", self.outline_color)
        )
        self.glow_color_row = _row("Цвет свечения", self.glow_color)
        self.glow_opacity_row = _row("Сила свечения", self.glow_opacity)
        self.glow_radius_row = _row("Радиус свечения", self.glow_radius)
        advanced.content_layout.addWidget(self.glow_color_row)
        advanced.content_layout.addWidget(self.glow_opacity_row)
        advanced.content_layout.addWidget(self.glow_radius_row)
        layout.addWidget(advanced)

        self.animation_group: QGroupBox | None = None
        if include_animation:
            self.animation_group = QGroupBox("Появление подхука")
            animation_layout = QVBoxLayout(self.animation_group)
            animation_layout.setSpacing(12)
            self.animation = QComboBox()
            self.animation.addItem(
                "Без анимации — виден с начала",
                SubhookAnimation.NONE.value,
            )
            self.animation.addItem(
                "Вылет снизу с отскоком",
                SubhookAnimation.SLIDE_BOUNCE.value,
            )
            self.animation.addItem(
                "Увеличение из точки с отскоком",
                SubhookAnimation.ZOOM_BOUNCE.value,
            )
            self.appear_at = SliderSpin(
                0.0,
                5.5,
                decimals=1,
                step=0.1,
                suffix=" сек.",
            )
            animation_layout.addWidget(
                _row("Анимация", self.animation)
            )
            self.appear_row = _row(
                "Начать на секунде",
                self.appear_at,
                "Настройка не используется, если выбрано «Без анимации».",
            )
            animation_layout.addWidget(self.appear_row)
            self.animation.currentIndexChanged.connect(
                self._update_animation_state
            )
            layout.addWidget(self.animation_group)

        layout.addStretch(1)
        self.preset.currentIndexChanged.connect(self._apply_preset)
        self.background_style.currentIndexChanged.connect(
            self._update_style_state
        )
        self._update_style_state()

    def load(
        self,
        style: TextStyleSettings,
        animation: SubhookAnimationSettings | None = None,
    ) -> None:
        self.preset.blockSignals(True)
        self.preset.setCurrentIndex(0)
        self.preset.blockSignals(False)
        self.font.set_value(style.font)
        self.font_size.set_value(style.font_size)
        self.text_color.set_value(style.text_color)
        self._set_combo_data(self.background_style, style.background_style)
        self.background_color.set_value(style.background_color)
        self.background_opacity.set_value(style.background_opacity)
        self.background_padding.set_value(style.background_padding)
        self.background_corner_radius.set_value(style.background_corner_radius)
        self.outline_width.set_value(style.outline_width)
        self.outline_color.set_value(style.outline_color)
        self.glow_color.set_value(style.glow_color)
        self.glow_opacity.set_value(style.glow_opacity)
        self.glow_radius.set_value(style.glow_radius)
        if self.include_animation and animation is not None:
            self._set_combo_data(self.animation, animation.animation)
            self.appear_at.set_value(animation.appear_at)
            self._update_animation_state()
        self._update_style_state()

    def style(self) -> TextStyleSettings:
        return TextStyleSettings(
            font=self.font.value(),
            font_size=int(self.font_size.value()),
            text_color=self.text_color.value(),
            outline_width=int(self.outline_width.value()),
            outline_color=self.outline_color.value(),
            background_style=BackgroundStyle(
                self.background_style.currentData()
            ),
            background_color=self.background_color.value(),
            background_opacity=int(self.background_opacity.value()),
            background_padding=int(self.background_padding.value()),
            background_corner_radius=int(
                self.background_corner_radius.value()
            ),
            glow_color=self.glow_color.value(),
            glow_opacity=int(self.glow_opacity.value()),
            glow_radius=int(self.glow_radius.value()),
        )

    def animation_settings(self) -> SubhookAnimationSettings:
        if not self.include_animation:
            return SubhookAnimationSettings()
        return SubhookAnimationSettings(
            animation=SubhookAnimation(self.animation.currentData()),
            appear_at=float(self.appear_at.value()),
        )

    @staticmethod
    def _set_combo_data(combo: QComboBox, value) -> None:
        index = combo.findData(getattr(value, "value", value))
        if index >= 0:
            combo.setCurrentIndex(index)

    def _apply_preset(self, index: int) -> None:
        values = STYLE_PRESETS[index][1]
        if not values:
            return
        controls = {
            "text_color": self.text_color,
            "background_color": self.background_color,
            "background_opacity": self.background_opacity,
            "background_padding": self.background_padding,
            "background_corner_radius": self.background_corner_radius,
            "outline_width": self.outline_width,
            "outline_color": self.outline_color,
            "glow_color": self.glow_color,
            "glow_opacity": self.glow_opacity,
            "glow_radius": self.glow_radius,
        }
        for name, value in values.items():
            if name == "background_style":
                self._set_combo_data(self.background_style, value)
            else:
                controls[name].set_value(value)
        self._update_style_state()

    def _update_style_state(self, _index: int = -1) -> None:
        style = BackgroundStyle(self.background_style.currentData())
        uses_background = style in {
            BackgroundStyle.RECTANGLE,
            BackgroundStyle.LINES,
            BackgroundStyle.TORN_PAPER,
            BackgroundStyle.PAPER_LETTERS,
        }
        self.background_group.setVisible(uses_background)
        self.corner_row.setVisible(
            style in {BackgroundStyle.RECTANGLE, BackgroundStyle.LINES}
        )
        uses_glow = style == BackgroundStyle.GLOW
        for row in (
            self.glow_color_row,
            self.glow_opacity_row,
            self.glow_radius_row,
        ):
            row.setVisible(uses_glow)

    def _update_animation_state(self, _index: int = -1) -> None:
        if self.include_animation:
            self.appear_row.setEnabled(
                SubhookAnimation(self.animation.currentData())
                != SubhookAnimation.NONE
            )


class SettingsDialog(QDialog):
    def __init__(
        self,
        settings_path: str | Path,
        fonts_dir: str | Path,
        parent=None,
    ):
        super().__init__(parent)
        self.settings_path = Path(settings_path)
        self.fonts_dir = Path(fonts_dir)
        self.test_requested = False
        self.setWindowTitle("Настроить ролики")
        self.setModal(True)
        self.setMinimumSize(900, 690)
        self.resize(1020, 820)

        warning_text = ""
        try:
            initial = load_settings(self.settings_path)
        except SettingsError as exc:
            initial = default_settings()
            warning_text = (
                "Текущий settings.ini содержит ошибку. Показаны стандартные "
                f"значения; сохранение исправит файл.\n{exc}"
            )

        root = QVBoxLayout(self)
        root.setContentsMargins(22, 20, 22, 20)
        root.setSpacing(14)
        title = QLabel("Настроить ролики")
        title.setObjectName("DialogTitle")
        root.addWidget(title)
        subtitle = QLabel(
            "Выберите понятные готовые варианты или укажите точные значения. "
            "Все настройки сохраняются в папке программы."
        )
        subtitle.setObjectName("SettingsHint")
        subtitle.setWordWrap(True)
        root.addWidget(subtitle)

        self.warning = QLabel(warning_text)
        self.warning.setObjectName("SettingsWarning")
        self.warning.setWordWrap(True)
        self.warning.setVisible(bool(warning_text))
        root.addWidget(self.warning)

        self.tabs = QTabWidget()
        self.tabs.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Ignored,
        )
        self.tabs.setMinimumHeight(420)
        self.general_editor = GeneralSettingsEditor()
        self.hook_editor = TextStyleEditor(
            self.fonts_dir,
            role_name="Хук",
        )
        self.subhook_editor = TextStyleEditor(
            self.fonts_dir,
            role_name="Подхук",
            include_animation=True,
        )
        self.hook_editor.font.font_added.connect(
            lambda _name: self.subhook_editor.font.refresh()
        )
        self.subhook_editor.font.font_added.connect(
            lambda _name: self.hook_editor.font.refresh()
        )
        self.tabs.addTab(self._scroll(self.general_editor), "Общие")
        self.tabs.addTab(self._scroll(self.hook_editor), "Хук")
        self.tabs.addTab(self._scroll(self.subhook_editor), "Подхук")
        root.addWidget(self.tabs, 1)

        self.status = QLabel("")
        self.status.setObjectName("SettingsHint")
        self.status.setWordWrap(True)
        root.addWidget(self.status)

        buttons = QHBoxLayout()
        self.reset_button = QPushButton("Вернуть стандартные настройки")
        self.cancel_button = QPushButton("Отмена")
        self.save_button = QPushButton("Сохранить")
        self.save_test_button = QPushButton("Сохранить и протестировать")
        self.save_test_button.setObjectName("PrimaryButton")
        buttons.addWidget(self.reset_button)
        buttons.addStretch(1)
        buttons.addWidget(self.cancel_button)
        buttons.addWidget(self.save_button)
        buttons.addWidget(self.save_test_button)
        root.addLayout(buttons)

        self.reset_button.clicked.connect(self._reset_defaults)
        self.cancel_button.clicked.connect(self.reject)
        self.save_button.clicked.connect(lambda: self._save(False))
        self.save_test_button.clicked.connect(lambda: self._save(True))
        self.load(initial)

    @staticmethod
    def _scroll(widget: QWidget) -> QScrollArea:
        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setFrameShape(QFrame.Shape.NoFrame)
        area.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Ignored,
        )
        area.setMinimumSize(0, 0)
        area.setWidget(widget)
        return area

    def load(self, settings: AppSettings) -> None:
        self.general_editor.load(settings.general)
        self.hook_editor.load(settings.hook)
        self.subhook_editor.load(
            settings.subhook,
            settings.subhook_animation,
        )

    def settings(self) -> AppSettings:
        return AppSettings(
            general=self.general_editor.settings(),
            hook=self.hook_editor.style(),
            subhook=self.subhook_editor.style(),
            subhook_animation=self.subhook_editor.animation_settings(),
        )

    def _reset_defaults(self) -> None:
        self.load(default_settings())
        self.status.setText(
            "Стандартные значения загружены в форму. "
            "Чтобы применить их, нажмите «Сохранить»."
        )
        self.status.setStyleSheet(f"color: {ACCENT};")

    def _save(self, test_requested: bool) -> None:
        try:
            settings = self.settings()
            save_settings(self.settings_path, settings)
        except SettingsError as exc:
            QMessageBox.critical(
                self,
                "Проверьте настройки",
                str(exc),
            )
            return
        self.test_requested = test_requested
        self.accept()
