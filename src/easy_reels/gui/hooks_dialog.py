from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from ..excel import HooksWorkbook
from ..models import HookEditorRow
from .theme import MUTED


class HooksDialog(QDialog):
    """Edit hooks without requiring Microsoft Excel or another office suite."""

    HEADERS = ("Хук", "Подхук", "Описание", "Готовый файл", "Статус")
    EDITABLE_COLUMNS = 3

    def __init__(
        self,
        workbook_path: str | Path,
        backup_dir: str | Path,
        parent=None,
    ):
        super().__init__(parent)
        self.workbook_path = Path(workbook_path)
        self.backup_dir = Path(backup_dir)
        self._loading = False

        self.setWindowTitle("Редактор хуков")
        self.setModal(True)
        self.resize(1180, 720)
        self.setMinimumSize(820, 520)
        self._build_ui()
        self._load_rows()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(13)

        title = QLabel("Хуки и подхуки")
        title.setObjectName("DialogTitle")
        layout.addWidget(title)

        hint = QLabel(
            "Заполняйте первые три столбца прямо здесь. Microsoft Excel не нужен. "
            "Если изменить уже обработанную строку, её результат будет сброшен и ролик можно создать заново."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color: {MUTED};")
        layout.addWidget(hint)

        toolbar = QHBoxLayout()
        self.add_button = QPushButton("Добавить строку")
        self.paste_button = QPushButton("Вставить список")
        self.delete_button = QPushButton("Удалить выбранные")
        self.reset_button = QPushButton("Сбросить результат")
        toolbar.addWidget(self.add_button)
        toolbar.addWidget(self.paste_button)
        toolbar.addWidget(self.delete_button)
        toolbar.addWidget(self.reset_button)
        toolbar.addStretch(1)
        layout.addLayout(toolbar)

        self.table = QTableWidget(0, len(self.HEADERS))
        self.table.setHorizontalHeaderLabels(self.HEADERS)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
            | QAbstractItemView.EditTrigger.SelectedClicked
        )
        self.table.verticalHeader().setDefaultSectionSize(48)
        header = self.table.horizontalHeader()
        for column in range(len(self.HEADERS)):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.table, 1)

        footer = QHBoxLayout()
        self.count_label = QLabel("")
        self.count_label.setStyleSheet(f"color: {MUTED};")
        self.cancel_button = QPushButton("Отмена")
        self.save_button = QPushButton("Сохранить")
        self.save_button.setObjectName("PrimaryButton")
        footer.addWidget(self.count_label)
        footer.addStretch(1)
        footer.addWidget(self.cancel_button)
        footer.addWidget(self.save_button)
        layout.addLayout(footer)

        self.add_button.clicked.connect(self._add_empty_row)
        self.paste_button.clicked.connect(self._paste_rows)
        self.delete_button.clicked.connect(self._delete_selected)
        self.reset_button.clicked.connect(self._reset_selected)
        self.cancel_button.clicked.connect(self.reject)
        self.save_button.clicked.connect(self._save)
        self.table.cellChanged.connect(self._on_cell_changed)

    def _load_rows(self) -> None:
        try:
            workbook = HooksWorkbook(self.workbook_path)
            rows = workbook.editor_rows()
        except Exception as exc:
            QMessageBox.critical(self, "Не удалось открыть хуки", str(exc))
            self.reject()
            return
        self._loading = True
        try:
            self.table.setRowCount(0)
            for row in rows:
                self._append_row(row)
            if not rows:
                self._append_row(HookEditorRow())
        finally:
            self._loading = False
        self._update_count()

    def _append_row(self, values: HookEditorRow) -> int:
        row = self.table.rowCount()
        self.table.insertRow(row)
        texts = (
            values.hook,
            values.subhook,
            values.description,
            values.ready_file,
            values.status,
        )
        for column, text in enumerate(texts):
            item = QTableWidgetItem(text)
            item.setToolTip(text)
            if column >= self.EDITABLE_COLUMNS:
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, column, item)
        return row

    @Slot()
    def _add_empty_row(self) -> None:
        row = self._append_row(HookEditorRow())
        self.table.setCurrentCell(row, 0)
        self.table.editItem(self.table.item(row, 0))
        self._update_count()

    def _selected_rows(self) -> list[int]:
        selection = sorted(
            {index.row() for index in self.table.selectionModel().selectedRows()}
        )
        if not selection and self.table.currentRow() >= 0:
            selection = [self.table.currentRow()]
        return selection

    @Slot()
    def _delete_selected(self) -> None:
        for row in reversed(self._selected_rows()):
            self.table.removeRow(row)
        if self.table.rowCount() == 0:
            self._append_row(HookEditorRow())
        self._update_count()

    @Slot()
    def _reset_selected(self) -> None:
        rows = self._selected_rows()
        if not rows:
            QMessageBox.information(self, "Строки не выбраны", "Выберите строки для повторной генерации.")
            return
        self._loading = True
        try:
            for row in rows:
                for column in (3, 4):
                    item = self.table.item(row, column)
                    if item is None:
                        item = QTableWidgetItem("")
                        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                        self.table.setItem(row, column, item)
                    else:
                        item.setText("")
        finally:
            self._loading = False

    @Slot()
    def _paste_rows(self) -> None:
        text = QApplication.clipboard().text().replace("\r\n", "\n").replace("\r", "\n")
        lines = [line for line in text.split("\n") if line.strip()]
        if not lines:
            QMessageBox.information(self, "Буфер пуст", "Скопируйте список хуков и повторите попытку.")
            return
        start = self.table.rowCount()
        if start == 1 and self._row_is_empty(0):
            self.table.removeRow(0)
            start = 0
        self._loading = True
        try:
            for line in lines:
                columns = [part.strip() for part in line.split("\t")]
                columns += [""] * (3 - len(columns))
                self._append_row(
                    HookEditorRow(
                        hook=columns[0],
                        subhook=columns[1],
                        description=columns[2],
                    )
                )
        finally:
            self._loading = False
        self.table.setCurrentCell(start, 0)
        self._update_count()

    def _row_is_empty(self, row: int) -> bool:
        return not any(self._text(row, column) for column in range(len(self.HEADERS)))

    def _text(self, row: int, column: int) -> str:
        item = self.table.item(row, column)
        return item.text().strip() if item else ""

    @Slot(int, int)
    def _on_cell_changed(self, row: int, column: int) -> None:
        if self._loading or column >= self.EDITABLE_COLUMNS:
            return
        self._loading = True
        try:
            for result_column in (3, 4):
                item = self.table.item(row, result_column)
                if item is not None:
                    item.setText("")
        finally:
            self._loading = False
        self._update_count()

    def _collect_rows(self) -> list[HookEditorRow] | None:
        result: list[HookEditorRow] = []
        for row in range(self.table.rowCount()):
            values = [self._text(row, column) for column in range(len(self.HEADERS))]
            if not any(values):
                continue
            if not values[0]:
                QMessageBox.warning(
                    self,
                    "Не заполнен хук",
                    f"В строке {row + 1} заполнены другие поля, но нет хука.",
                )
                self.table.setCurrentCell(row, 0)
                return None
            result.append(HookEditorRow(*values))
        return result

    @Slot()
    def _save(self) -> None:
        rows = self._collect_rows()
        if rows is None:
            return
        try:
            workbook = HooksWorkbook(self.workbook_path)
            workbook.create_backup(self.backup_dir)
            workbook.replace_editor_rows(rows)
            workbook.save()
        except Exception as exc:
            QMessageBox.critical(self, "Не удалось сохранить хуки", str(exc))
            return
        self.accept()

    def _update_count(self) -> None:
        filled = sum(
            1 for row in range(self.table.rowCount()) if self._text(row, 0)
        )
        self.count_label.setText(f"Хуков: {filled}")
