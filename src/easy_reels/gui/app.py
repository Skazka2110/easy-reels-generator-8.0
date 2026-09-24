from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

from .. import __version__
from ..errors import LicenseConfigurationError
from ..licensing import LicenseManager, load_client_config
from ..paths import ProjectPaths
from .activation import ActivationDialog
from .main_window import MainWindow
from .theme import STYLESHEET


ASSET_DIR = Path(__file__).resolve().parent.parent / "assets"


def default_project_root() -> Path:
    if getattr(sys, "frozen", False):
        executable = Path(sys.executable).resolve()
        if sys.platform == "darwin":
            for parent in executable.parents:
                if parent.suffix.casefold() == ".app":
                    return parent.parent
        return executable.parent
    return Path.cwd()


def user_data_dir() -> Path:
    if sys.platform == "darwin":
        return (
            Path.home()
            / "Library"
            / "Application Support"
            / "ProAI Studio"
            / "Easy Reels Generator"
        )
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return base / "ProAI Studio" / "Easy Reels Generator"
    base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / "proai-studio" / "easy-reels-generator"


def bundled_tool(name: str) -> str:
    """Return a tool shipped next to the portable executable when available."""
    executable_name = f"{name}.exe" if sys.platform == "win32" else name
    if getattr(sys, "frozen", False):
        executable = Path(sys.executable).resolve()
        candidates = [executable.parent / executable_name]
        bundle_root = Path(getattr(sys, "_MEIPASS", executable.parent)).resolve()
        candidates.extend(
            (
                bundle_root / executable_name,
                bundle_root / "_internal" / executable_name,
            )
        )
        if sys.platform == "darwin":
            for parent in executable.parents:
                if parent.suffix.casefold() == ".app":
                    candidates.extend(
                        (
                            parent / "Contents" / "MacOS" / executable_name,
                            parent / "Contents" / "Frameworks" / executable_name,
                            parent / "Contents" / "Resources" / executable_name,
                        )
                    )
                    break
        for candidate in candidates:
            if candidate.is_file():
                return str(candidate)
    return executable_name


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("--project", default=str(default_project_root()))
    parser.add_argument("--ffmpeg", default=bundled_tool("ffmpeg"))
    parser.add_argument("--ffprobe", default=bundled_tool("ffprobe"))
    parser.add_argument("--encoder", default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    application = QApplication.instance() or QApplication(sys.argv[:1])
    application.setApplicationName("Easy Reels Generator by ProAI")
    application.setOrganizationName("ProAI Studio")
    application.setStyle("Fusion")
    application.setFont(QFont("Segoe UI", 10))
    application.setStyleSheet(STYLESHEET)
    project_paths = ProjectPaths.from_root(args.project)
    project_paths.ensure_directories()
    try:
        license_config = load_client_config(ASSET_DIR / "license_config.json")
        data_dir = user_data_dir()
        license_manager = LicenseManager(
            license_config,
            data_dir / "license.json",
            app_version=__version__,
            legacy_license_paths=(project_paths.licenses / "license.json",),
            log_path=data_dir / "activation.log",
        )
    except LicenseConfigurationError as exc:
        QMessageBox.critical(
            None,
            "Easy Reels Generator",
            f"Не удалось подготовить активацию:\n{exc}",
        )
        return 2
    license_status = license_manager.check()
    if not license_status.valid:
        activation = ActivationDialog(
            license_manager,
            icon_path=ASSET_DIR / "icon.png",
            initial_message=license_status.message,
        )
        if activation.exec() != QDialog.Accepted:
            return 0
        license_status = license_manager.check()
        if not license_status.valid:
            QMessageBox.critical(
                None,
                "Easy Reels Generator",
                "Активация не сохранилась. Повторите запуск программы.",
            )
            return 2
    window = MainWindow(
        args.project,
        ffmpeg=args.ffmpeg,
        ffprobe=args.ffprobe,
        encoder=args.encoder,
        license_text=license_status.message,
    )
    window.show()
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
