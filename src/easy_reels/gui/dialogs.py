from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)


class ConfirmBatchDialog(QDialog):
    def __init__(self, report, estimated_size_mb: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Проверка перед запуском")
        self.setModal(True)
        self.setMinimumWidth(480)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        title = QLabel("Всё готово к генерации")
        title.setObjectName("SectionTitle")
        layout.addWidget(title)
        text = QLabel(
            "Проверьте объём партии. Ролики будут создаваться последовательно, "
            "а список хуков сохранится после каждого результата."
        )
        text.setWordWrap(True)
        layout.addWidget(text)

        summary = QFrame()
        summary.setObjectName("StatusCard")
        summary_layout = QVBoxLayout(summary)
        summary_layout.setContentsMargins(18, 14, 18, 14)
        summary_layout.setSpacing(7)
        music = (
            f"{report.valid_music} аудиофайл(а)"
            if report.valid_music
            else "без музыки"
        )
        for value in (
            f"Роликов к созданию: {report.pending_rows}",
            f"Видео: {report.valid_videos}",
            f"Музыка: {music}",
            f"Ориентировочно потребуется: до {estimated_size_mb} МБ",
        ):
            summary_layout.addWidget(QLabel(value))
        layout.addWidget(summary)

        buttons = QDialogButtonBox()
        cancel = buttons.addButton("Отмена", QDialogButtonBox.RejectRole)
        start = buttons.addButton("Начать генерацию", QDialogButtonBox.AcceptRole)
        start.setObjectName("PrimaryButton")
        cancel.clicked.connect(self.reject)
        start.clicked.connect(self.accept)
        layout.addWidget(buttons)


class CompletionDialog(QDialog):
    def __init__(self, result, ready_dir: Path, workbook: Path, parent=None):
        super().__init__(parent)
        self.open_hooks_requested = False
        self.setWindowTitle("Генерация завершена")
        self.setModal(True)
        self.setMinimumWidth(500)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(15)

        title_text = "Генерация остановлена" if result.stopped else "Генерация завершена"
        title = QLabel(title_text)
        title.setObjectName("SectionTitle")
        layout.addWidget(title)
        layout.addWidget(
            QLabel(
                f"Создано роликов: {len(result.created_files)}\n"
                f"Ошибок строк: {len(result.row_errors)}\n"
                f"Обработано: {result.processed} из {result.total}"
            )
        )

        actions = QHBoxLayout()
        ready_button = QPushButton("Открыть готовые ролики")
        ready_button.setObjectName("PrimaryButton")
        ready_button.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(ready_dir)))
        )
        excel_button = QPushButton("Открыть хуки")
        excel_button.clicked.connect(self._open_hooks)
        actions.addWidget(ready_button)
        actions.addWidget(excel_button)
        layout.addLayout(actions)

        close_button = QPushButton("Закрыть")
        close_button.clicked.connect(self.accept)
        layout.addWidget(close_button)

    def _open_hooks(self) -> None:
        self.open_hooks_requested = True
        self.accept()
