from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QThread, Qt, Signal, Slot
from PySide6.QtGui import QCloseEvent, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from ..errors import LicenseActivationError
from .theme import ACCENT, ERROR, MUTED, neon_shadow


class ActivationWorker(QObject):
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, manager, key: str):
        super().__init__()
        self.manager = manager
        self.key = key

    @Slot()
    def run(self) -> None:
        try:
            result = self.manager.activate(self.key)
        except LicenseActivationError as exc:
            self.failed.emit(str(exc))
            return
        except Exception:
            self.failed.emit(
                "Не удалось завершить активацию. Проверьте интернет и повторите попытку."
            )
            return
        self.finished.emit(result)


class ActivationDialog(QDialog):
    def __init__(
        self,
        manager,
        *,
        icon_path: str | Path | None = None,
        initial_message: str = "",
        parent=None,
    ):
        super().__init__(parent)
        self.manager = manager
        self._thread: QThread | None = None
        self._worker = None

        self.setWindowTitle("Активация Easy Reels Generator")
        self.setModal(True)
        self.setMinimumWidth(540)
        self.setMaximumWidth(620)
        self._build_ui(Path(icon_path) if icon_path else None, initial_message)

    def _build_ui(self, icon_path: Path | None, initial_message: str) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 26, 28, 26)
        layout.setSpacing(17)

        header = QHBoxLayout()
        if icon_path and icon_path.is_file():
            logo = QLabel()
            logo.setFixedSize(58, 58)
            logo.setPixmap(
                QPixmap(str(icon_path)).scaled(
                    58, 58, Qt.KeepAspectRatio, Qt.SmoothTransformation
                )
            )
            neon_shadow(logo, blur=22, strength=110)
            header.addWidget(logo)
        titles = QVBoxLayout()
        title = QLabel("Активируйте программу")
        title.setObjectName("AppTitle")
        subtitle = QLabel("Easy Reels Generator by ProAI")
        subtitle.setStyleSheet(f"color: {ACCENT}; font-weight: 700;")
        titles.addWidget(title)
        titles.addWidget(subtitle)
        header.addLayout(titles)
        header.addStretch(1)
        layout.addLayout(header)

        explanation = QLabel(
            "Введите ключ, полученный после покупки. Он бессрочно привяжется "
            "к этому устройству. Интернет нужен только для первой активации."
        )
        explanation.setWordWrap(True)
        layout.addWidget(explanation)

        key_panel = QFrame()
        key_panel.setObjectName("StatusCard")
        key_layout = QVBoxLayout(key_panel)
        key_layout.setContentsMargins(18, 16, 18, 17)
        key_layout.setSpacing(9)
        key_label = QLabel("Лицензионный ключ")
        key_label.setStyleSheet(f"color: {MUTED}; font-size: 12px;")
        self.key_input = QLineEdit()
        self.key_input.setPlaceholderText("ERG-XXXX-XXXX-XXXX-XXXX")
        self.key_input.setMaxLength(40)
        self.key_input.setClearButtonEnabled(True)
        self.key_input.returnPressed.connect(self.start_activation)
        key_layout.addWidget(key_label)
        key_layout.addWidget(self.key_input)
        layout.addWidget(key_panel)

        self.status_label = QLabel(initial_message or "Ключ будет проверен защищённым сервером ProAI.")
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet(f"color: {MUTED};")
        layout.addWidget(self.status_label)

        actions = QHBoxLayout()
        self.cancel_button = QPushButton("Закрыть программу")
        self.activate_button = QPushButton("Активировать")
        self.activate_button.setObjectName("PrimaryButton")
        neon_shadow(self.activate_button, blur=20, strength=75)
        self.cancel_button.clicked.connect(self.reject)
        self.activate_button.clicked.connect(self.start_activation)
        actions.addWidget(self.cancel_button)
        actions.addStretch(1)
        actions.addWidget(self.activate_button)
        layout.addLayout(actions)

        self.key_input.setFocus()

    @Slot()
    def start_activation(self) -> None:
        if self._thread is not None:
            return
        key = self.key_input.text().strip()
        if not key:
            self._show_error("Введите лицензионный ключ.")
            return
        worker = ActivationWorker(self.manager, key)
        thread = QThread(self)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(self._activation_succeeded)
        worker.failed.connect(self._activation_failed)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        worker.failed.connect(worker.deleteLater)
        thread.finished.connect(self._thread_finished)
        thread.finished.connect(thread.deleteLater)
        self._worker = worker
        self._thread = thread
        self._set_busy(True)
        thread.start()

    def _set_busy(self, busy: bool) -> None:
        self.key_input.setEnabled(not busy)
        self.cancel_button.setEnabled(not busy)
        self.activate_button.setEnabled(not busy)
        self.activate_button.setText("Проверяем…" if busy else "Активировать")
        if busy:
            self.status_label.setText("Соединяемся с сервером активации…")
            self.status_label.setStyleSheet(f"color: {ACCENT};")

    @Slot(object)
    def _activation_succeeded(self, result) -> None:
        self.status_label.setText(result.message)
        self.status_label.setStyleSheet(f"color: {ACCENT}; font-weight: 700;")
        self.accept()

    @Slot(str)
    def _activation_failed(self, message: str) -> None:
        self._show_error(message)

    def _thread_finished(self) -> None:
        self._thread = None
        self._worker = None
        self._set_busy(False)

    def _show_error(self, message: str) -> None:
        self.status_label.setText(message)
        self.status_label.setStyleSheet(f"color: {ERROR}; font-weight: 600;")

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._thread is not None:
            self.status_label.setText("Дождитесь ответа сервера активации.")
            event.ignore()
            return
        event.accept()
