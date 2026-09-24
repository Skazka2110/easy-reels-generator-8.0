import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from easy_reels.excel import HooksWorkbook, create_workbook_template
from easy_reels.gui.hooks_dialog import HooksDialog
from easy_reels.models import HookEditorRow


def test_editing_hook_resets_previous_result(tmp_path: Path) -> None:
    app = QApplication.instance() or QApplication([])
    workbook_path = tmp_path / "hooks.xlsx"
    create_workbook_template(workbook_path)
    workbook = HooksWorkbook(workbook_path)
    workbook.replace_editor_rows(
        [HookEditorRow("Старый хук", ready_file="old.mp4", status="Готово")]
    )
    workbook.save()

    dialog = HooksDialog(workbook_path, tmp_path / "backups")
    dialog.table.item(0, 0).setText("Новый хук")

    assert dialog.table.item(0, 3).text() == ""
    assert dialog.table.item(0, 4).text() == ""
    dialog._save()

    rows = HooksWorkbook(workbook_path).editor_rows()
    assert rows == [HookEditorRow("Новый хук")]
    assert list((tmp_path / "backups").glob("hooks_*.xlsx"))
    app.processEvents()
