from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThread, QTimer, Qt, QUrl
from PySide6.QtGui import QCloseEvent, QDesktopServices, QIcon, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpacerItem,
    QVBoxLayout,
    QWidget,
)

from .. import __version__
from ..config import load_settings
from ..excel import HooksWorkbook
from ..media import AUDIO_EXTENSIONS, VIDEO_EXTENSIONS, discover_files
from ..pipeline import ReelsPipeline
from ..paths import ProjectPaths
from .dialogs import CompletionDialog, ConfirmBatchDialog
from .hooks_dialog import HooksDialog
from .settings_dialog import SettingsDialog
from .theme import ACCENT, ERROR, MUTED, WARNING, neon_shadow
from .workers import BatchWorker, PreviewWorker


ASSET_DIR = Path(__file__).resolve().parent.parent / "assets"


class StatusCard(QFrame):
    def __init__(self, title: str, object_name: str, parent=None):
        super().__init__(parent)
        self.setObjectName("StatusCard")
        self.setProperty("cardName", object_name)
        self.setMinimumHeight(126)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(17, 15, 17, 15)
        layout.setSpacing(7)

        header = QHBoxLayout()
        title_label = QLabel(title)
        title_label.setObjectName("CardTitle")
        self.dot = QLabel("●")
        self.dot.setFixedWidth(18)
        header.addWidget(title_label)
        header.addStretch(1)
        header.addWidget(self.dot)
        layout.addLayout(header)

        self.value = QLabel("Проверка…")
        self.value.setObjectName("CardValue")
        self.value.setWordWrap(True)
        layout.addWidget(self.value)
        self.detail = QLabel("")
        self.detail.setObjectName("CardDetail")
        self.detail.setWordWrap(True)
        layout.addWidget(self.detail)
        layout.addStretch(1)

    def set_state(self, value: str, detail: str, tone: str = "ok") -> None:
        colors = {"ok": ACCENT, "warning": WARNING, "error": ERROR, "muted": MUTED}
        self.dot.setStyleSheet(f"color: {colors.get(tone, MUTED)}; background: transparent;")
        self.value.setText(value)
        self.detail.setText(detail)


class MainWindow(QMainWindow):
    def __init__(
        self,
        project_root: str | Path,
        *,
        ffmpeg: str = "ffmpeg",
        ffprobe: str = "ffprobe",
        encoder: str | None = None,
        license_text: str = "Лицензия: режим разработки",
    ):
        super().__init__()
        self.paths = ProjectPaths.from_root(project_root)
        self.pipeline = ReelsPipeline(
            self.paths.root, ffmpeg=ffmpeg, ffprobe=ffprobe, encoder=encoder
        )
        self._thread: QThread | None = None
        self._worker = None
        self._active_mode: str | None = None
        self._close_after_finish = False

        self.setWindowTitle("Easy Reels Generator by ProAI")
        icon_path = ASSET_DIR / "icon.png"
        if icon_path.is_file():
            self.setWindowIcon(QIcon(str(icon_path)))
        self.setMinimumSize(960, 700)
        self.resize(1120, 780)
        self._build_ui(icon_path, license_text)
        self.refresh_snapshot()

    def _build_ui(self, icon_path: Path, license_text: str) -> None:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        central = QWidget()
        scroll.setWidget(central)
        self.setCentralWidget(scroll)
        root = QVBoxLayout(central)
        root.setContentsMargins(28, 25, 28, 24)
        root.setSpacing(18)

        header = QFrame()
        header.setObjectName("HeaderPanel")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(20, 17, 20, 17)
        header_layout.setSpacing(16)
        logo = QLabel()
        logo.setFixedSize(62, 62)
        if icon_path.is_file():
            logo.setPixmap(
                QPixmap(str(icon_path)).scaled(
                    62, 62, Qt.KeepAspectRatio, Qt.SmoothTransformation
                )
            )
            neon_shadow(logo, blur=24, strength=115)
        header_layout.addWidget(logo)
        titles = QVBoxLayout()
        titles.setSpacing(2)
        title = QLabel("Easy Reels Generator")
        title.setObjectName("AppTitle")
        brand = QLabel("by ProAI")
        brand.setObjectName("BrandLabel")
        titles.addWidget(title)
        titles.addWidget(brand)
        header_layout.addLayout(titles)
        header_layout.addStretch(1)
        self.license_label = QLabel(license_text)
        self.license_label.setObjectName("LicensePill")
        if "активна" in license_text.casefold():
            self.license_label.setProperty("active", True)
        header_layout.addWidget(self.license_label)
        root.addWidget(header)

        section = QLabel("Проект")
        section.setObjectName("SectionTitle")
        root.addWidget(section)
        cards = QGridLayout()
        cards.setHorizontalSpacing(14)
        cards.setVerticalSpacing(14)
        self.excel_card = StatusCard("ХУКИ", "hooks")
        self.video_card = StatusCard("ВИДЕО", "video")
        self.music_card = StatusCard("МУЗЫКА", "music")
        self.settings_card = StatusCard("НАСТРОЙКИ", "settings")
        for index, card in enumerate(
            (self.excel_card, self.video_card, self.music_card, self.settings_card)
        ):
            cards.addWidget(card, 0, index)
            cards.setColumnStretch(index, 1)
        root.addLayout(cards)

        actions_title = QLabel("Действия")
        actions_title.setObjectName("SectionTitle")
        root.addWidget(actions_title)
        actions = QGridLayout()
        actions.setHorizontalSpacing(12)
        actions.setVerticalSpacing(11)
        self.open_excel_button = QPushButton("Редактировать хуки")
        self.open_settings_button = QPushButton("Настроить ролики")
        self.preview_button = QPushButton("Тестировать настройки")
        self.preview_button.setObjectName("PreviewButton")
        self.start_button = QPushButton("Запустить генерацию")
        self.start_button.setObjectName("PrimaryButton")
        neon_shadow(self.start_button, blur=22, strength=85)
        self.ready_button = QPushButton("Открыть готовые ролики")
        self.help_button = QPushButton("Как пользоваться")
        actions.addWidget(self.open_excel_button, 0, 0)
        actions.addWidget(self.open_settings_button, 0, 1)
        actions.addWidget(self.preview_button, 1, 0)
        actions.addWidget(self.start_button, 1, 1)
        actions.addWidget(self.ready_button, 2, 0)
        actions.addWidget(self.help_button, 2, 1)
        actions.setColumnStretch(0, 1)
        actions.setColumnStretch(1, 1)
        root.addLayout(actions)

        progress_panel = QFrame()
        progress_panel.setObjectName("ProgressPanel")
        progress_layout = QVBoxLayout(progress_panel)
        progress_layout.setContentsMargins(18, 14, 18, 14)
        progress_layout.setSpacing(9)
        progress_header = QHBoxLayout()
        self.progress_status = QLabel("Готово к работе")
        self.progress_status.setObjectName("SectionTitle")
        self.progress_numbers = QLabel("0 из 0")
        self.progress_numbers.setStyleSheet(f"color: {MUTED}; background: transparent;")
        progress_header.addWidget(self.progress_status)
        progress_header.addStretch(1)
        progress_header.addWidget(self.progress_numbers)
        progress_layout.addLayout(progress_header)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(0)
        progress_layout.addWidget(self.progress_bar)
        progress_actions = QHBoxLayout()
        self.progress_detail = QLabel("Проверьте файлы и запустите генерацию.")
        self.progress_detail.setStyleSheet(f"color: {MUTED}; background: transparent;")
        self.progress_detail.setWordWrap(True)
        self.stop_button = QPushButton("Остановить")
        self.stop_button.setObjectName("StopButton")
        self.stop_button.setEnabled(False)
        progress_actions.addWidget(self.progress_detail, 1)
        progress_actions.addWidget(self.stop_button)
        progress_layout.addLayout(progress_actions)
        root.addWidget(progress_panel)

        footer = QHBoxLayout()
        path_label = QLabel(f"Папка проекта: {self.paths.root}")
        path_label.setStyleSheet(f"color: {MUTED}; font-size: 11px;")
        version = QLabel(f"Версия ядра {__version__}")
        version.setStyleSheet(f"color: {MUTED}; font-size: 11px;")
        footer.addWidget(path_label)
        footer.addStretch(1)
        footer.addWidget(version)
        root.addLayout(footer)

        self.open_excel_button.clicked.connect(self._open_hooks)
        self.open_settings_button.clicked.connect(self._open_settings)
        self.ready_button.clicked.connect(
            lambda: self._open_path(self.paths.ready, "Папка ready не найдена.")
        )
        self.help_button.clicked.connect(self._open_help)
        self.preview_button.clicked.connect(self.start_preview)
        self.start_button.clicked.connect(self.confirm_and_start_batch)
        self.stop_button.clicked.connect(self.request_stop)

    def refresh_snapshot(self) -> None:
        self.paths.ensure_directories()
        try:
            workbook = HooksWorkbook(self.paths.workbook)
            pending = workbook.pending_rows(record_errors=False)
            self.excel_card.set_state(
                f"{len(pending)} к генерации",
                "Хуки доступны во встроенном редакторе",
                "ok" if pending else "warning",
            )
        except Exception as exc:
            self.excel_card.set_state("Нужна проверка", str(exc), "error")

        settings = None
        try:
            settings = load_settings(self.paths.settings)
            missing_fonts = [
                name
                for name in {settings.hook.font, settings.subhook.font}
                if not (self.paths.fonts / name).is_file()
            ]
            if missing_fonts:
                self.settings_card.set_state(
                    "Не хватает шрифтов",
                    ", ".join(sorted(missing_fonts)),
                    "error",
                )
            else:
                animation = settings.subhook_animation.animation.value
                animation_names = {
                    "slide_bounce": "вылет снизу",
                    "zoom_bounce": "увеличение из точки",
                }
                animation_detail = (
                    "без анимации"
                    if animation == "none"
                    else f"{animation_names[animation]} с "
                    f"{settings.subhook_animation.appear_at:g} сек."
                )
                self.settings_card.set_state(
                    "Загружены",
                    f"Хук: {settings.hook.font_size}px · подхук: "
                    f"{settings.subhook.font_size}px · {animation_detail}",
                    "ok",
                )
        except Exception as exc:
            self.settings_card.set_state("Ошибка файла", str(exc), "error")

        if settings is None:
            self.video_card.set_state(
                "Нужны настройки",
                "Не удалось определить папку top или bottom",
                "error",
            )
        else:
            video_directory = self.paths.videos_for_position(
                settings.general.hook_position
            )
            videos = discover_files(video_directory, VIDEO_EXTENSIONS)
            root_videos = discover_files(self.paths.videos, VIDEO_EXTENSIONS)
            relative_directory = video_directory.relative_to(self.paths.root).as_posix()
            detail = f"Используется только {relative_directory}"
            tone = "ok" if videos else "error"
            if root_videos:
                detail += f" · в videos пропущено: {len(root_videos)}"
                if videos:
                    tone = "warning"
            self.video_card.set_state(
                f"{len(videos)} файл(а)",
                detail,
                tone,
            )

        music = discover_files(self.paths.music, AUDIO_EXTENSIONS)
        self.music_card.set_state(
            f"{len(music)} файл(а)" if music else "Не добавлена",
            "Без музыки ролики будут бесшумными" if not music else "Музыка будет идти по кругу",
            "ok" if music else "muted",
        )

    def confirm_and_start_batch(self) -> None:
        try:
            report = self.pipeline.check()
        except Exception as exc:
            self._show_error(str(exc))
            self.refresh_snapshot()
            return
        if report.pending_rows == 0:
            QMessageBox.information(self, "Нет новых строк", "В редакторе нет хуков для генерации.")
            return
        dialog = ConfirmBatchDialog(
            report,
            estimated_size_mb=max(7, report.pending_rows * 7),
            parent=self,
        )
        if dialog.exec() != QDialog.Accepted:
            return
        worker = BatchWorker(self.pipeline)
        worker.progress.connect(self._on_progress)
        worker.finished.connect(self._on_batch_finished)
        worker.failed.connect(self._on_worker_failed)
        self._start_worker(worker, "batch")

    def start_preview(self) -> None:
        try:
            report = self.pipeline.check()
        except Exception as exc:
            self._show_error(str(exc))
            return
        if report.pending_rows == 0:
            QMessageBox.information(self, "Нет строки", "В редакторе нет хука для предпросмотра.")
            return
        worker = PreviewWorker(self.pipeline)
        worker.finished.connect(self._on_preview_finished)
        worker.failed.connect(self._on_worker_failed)
        self.progress_status.setText("Создаётся предпросмотр")
        self.progress_detail.setText(
            "Новый тестовый ролик появится в preview и не изменит таблицу."
        )
        self.progress_bar.setRange(0, 0)
        self._start_worker(worker, "preview")

    def _start_worker(self, worker, mode: str) -> None:
        if self._thread is not None:
            return
        thread = QThread(self)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        worker.failed.connect(worker.deleteLater)
        thread.finished.connect(self._thread_finished)
        thread.finished.connect(thread.deleteLater)
        self._thread = thread
        self._worker = worker
        self._active_mode = mode
        self._set_busy(True, allow_stop=(mode == "batch"))
        thread.start()

    def _thread_finished(self) -> None:
        self._thread = None
        self._worker = None
        self._active_mode = None
        self._set_busy(False)
        self.refresh_snapshot()
        if self._close_after_finish:
            self._close_after_finish = False
            QTimer.singleShot(0, self.close)

    def _set_busy(self, busy: bool, *, allow_stop: bool = False) -> None:
        for button in (
            self.open_excel_button,
            self.open_settings_button,
            self.preview_button,
            self.start_button,
        ):
            button.setEnabled(not busy)
        self.stop_button.setEnabled(busy and allow_stop)
        if not busy:
            self.stop_button.setText("Остановить")
            if self.progress_bar.maximum() == 0:
                self.progress_bar.setRange(0, 1)

    def _on_progress(self, update) -> None:
        self.progress_bar.setRange(0, max(1, update.total))
        self.progress_bar.setValue(update.processed)
        self.progress_numbers.setText(f"{update.processed} из {update.total}")
        self.progress_detail.setText(update.message)
        titles = {
            "preflight": "Проверка завершена",
            "rendering": "Создание роликов",
            "saved": "Результат сохранён",
            "row_error": "Есть ошибка строки",
            "stopped": "Генерация остановлена",
            "completed": "Генерация завершена",
        }
        self.progress_status.setText(titles.get(update.phase, "Генерация"))

    def request_stop(self) -> None:
        if isinstance(self._worker, BatchWorker):
            self._worker.request_stop()
            self.stop_button.setEnabled(False)
            self.stop_button.setText("Останавливаем…")
            self.progress_detail.setText(
                "Текущий ролик будет завершён и сохранён. Следующий не начнётся."
            )

    def _on_batch_finished(self, result) -> None:
        self.progress_status.setText(
            "Генерация остановлена" if result.stopped else "Генерация завершена"
        )
        self.progress_detail.setText(
            f"Создано: {len(result.created_files)} · ошибок: {len(result.row_errors)}"
        )
        dialog = CompletionDialog(
            result, self.paths.ready, self.paths.workbook, parent=self
        )
        dialog.exec()
        if dialog.open_hooks_requested:
            self._open_hooks()

    def _on_preview_finished(self, result) -> None:
        self.progress_status.setText("Предпросмотр готов")
        self.progress_detail.setText(str(result.output_path))
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(1)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(result.output_path)))

    def _on_worker_failed(self, message: str) -> None:
        self.progress_status.setText("Не удалось завершить операцию")
        self.progress_detail.setText(message)
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(0)
        self._show_error(message)

    def _open_path(self, path: Path, missing_message: str) -> None:
        if not path.exists():
            QMessageBox.warning(self, "Файл не найден", missing_message)
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def _open_settings(self) -> None:
        dialog = SettingsDialog(
            self.paths.settings,
            self.paths.fonts,
            parent=self,
        )
        if dialog.exec() != QDialog.Accepted:
            return
        self.refresh_snapshot()
        if dialog.test_requested:
            self.start_preview()

    def _open_hooks(self) -> None:
        dialog = HooksDialog(
            self.paths.workbook,
            self.paths.backups,
            parent=self,
        )
        dialog.exec()
        self.refresh_snapshot()

    def _open_help(self) -> None:
        instruction = self.paths.root / "Инструкция.pdf"
        if instruction.is_file():
            self._open_path(instruction, "Инструкция.pdf не найдена.")
        else:
            QMessageBox.information(
                self,
                "Инструкция",
                "Пользовательская инструкция будет добавлена в релизную папку после завершения интерфейса.",
            )

    def _show_error(self, message: str) -> None:
        QMessageBox.critical(self, "Easy Reels Generator", message)

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._thread is None:
            event.accept()
            return
        answer = QMessageBox.question(
            self,
            "Операция выполняется",
            "Сейчас создаётся видео. Запросить корректную остановку и закрыть окно после завершения текущего ролика?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer == QMessageBox.Yes:
            if isinstance(self._worker, BatchWorker):
                self.request_stop()
            self._close_after_finish = True
        event.ignore()
