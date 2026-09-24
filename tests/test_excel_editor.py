from pathlib import Path

from easy_reels.excel import HooksWorkbook, create_workbook_template
from easy_reels.models import HookEditorRow


def test_editor_rows_round_trip(tmp_path: Path) -> None:
    workbook_path = tmp_path / "hooks.xlsx"
    create_workbook_template(workbook_path)

    workbook = HooksWorkbook(workbook_path)
    workbook.replace_editor_rows(
        [
            HookEditorRow("Первый хук", "Подхук", "Описание"),
            HookEditorRow("Готовый хук", ready_file="video.mp4", status="Готово"),
        ]
    )
    workbook.save()

    reopened = HooksWorkbook(workbook_path)
    assert reopened.editor_rows() == [
        HookEditorRow("Первый хук", "Подхук", "Описание"),
        HookEditorRow("Готовый хук", ready_file="video.mp4", status="Готово"),
    ]
    assert [row.hook for row in reopened.pending_rows()] == ["Первый хук"]


def test_backup_is_created(tmp_path: Path) -> None:
    workbook_path = tmp_path / "hooks.xlsx"
    backup_dir = tmp_path / "backups"
    create_workbook_template(workbook_path)

    backup = HooksWorkbook(workbook_path).create_backup(backup_dir)

    assert backup.is_file()
    assert backup.name.startswith("hooks_")
