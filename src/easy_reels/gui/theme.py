from __future__ import annotations

from PySide6.QtGui import QColor
from PySide6.QtWidgets import QGraphicsDropShadowEffect, QWidget


BACKGROUND = "#0B0F0D"
PANEL = "#141A17"
PANEL_ALT = "#19211D"
ACCENT = "#39FF88"
ACCENT_DARK = "#14C96C"
TEXT = "#F3F7F4"
MUTED = "#8B9991"
WARNING = "#FFC857"
ERROR = "#FF5C6C"


STYLESHEET = f"""
QWidget {{
    background-color: {BACKGROUND};
    color: {TEXT};
    font-family: "Segoe UI", "Inter", "Arial";
    font-size: 14px;
}}
QMainWindow {{ background-color: {BACKGROUND}; }}
QLabel {{ background-color: transparent; }}
QFrame#HeaderPanel, QFrame#ProgressPanel {{
    background-color: {PANEL};
    border: 1px solid #243129;
    border-radius: 18px;
}}
QFrame#StatusCard {{
    background-color: {PANEL};
    border: 1px solid #26332C;
    border-radius: 16px;
}}
QFrame#StatusCard:hover {{ border-color: #3D5A49; }}
QLabel#AppTitle {{ font-size: 27px; font-weight: 700; }}
QLabel#BrandLabel {{ color: {ACCENT}; font-size: 14px; font-weight: 700; }}
QLabel#SectionTitle {{ font-size: 17px; font-weight: 700; }}
QLabel#DialogTitle {{ font-size: 24px; font-weight: 800; }}
QLabel#CardTitle {{ color: {MUTED}; font-size: 12px; font-weight: 600; }}
QLabel#CardValue {{ color: {TEXT}; font-size: 20px; font-weight: 700; }}
QLabel#CardDetail {{ color: {MUTED}; font-size: 12px; }}
QLabel#SettingsHint {{ color: {MUTED}; font-size: 12px; }}
QLabel#SettingsWarning {{
    color: {WARNING};
    background-color: #2B2414;
    border: 1px solid #5B4820;
    border-radius: 10px;
    padding: 10px 12px;
}}
QLabel#ValidationError {{ color: {ERROR}; font-size: 12px; }}
QLabel#FontSample {{
    color: {TEXT};
    background-color: #0F1511;
    border: 1px solid #304137;
    border-radius: 10px;
    padding: 8px 12px;
}}
QLabel#LicensePill {{
    color: {WARNING};
    background-color: #2B2414;
    border: 1px solid #5B4820;
    border-radius: 11px;
    padding: 5px 10px;
    font-size: 11px;
    font-weight: 600;
}}
QLabel#LicensePill[active="true"] {{
    color: {ACCENT};
    background-color: #10251A;
    border-color: #235F3B;
}}
QPushButton {{
    min-height: 42px;
    padding: 0 17px;
    border-radius: 12px;
    border: 1px solid #33443A;
    background-color: {PANEL_ALT};
    color: {TEXT};
    font-weight: 600;
}}
QPushButton:hover {{ border-color: {ACCENT_DARK}; background-color: #1D2A23; }}
QPushButton:pressed {{ background-color: #22352A; }}
QPushButton:disabled {{ color: #59645E; border-color: #252E29; background-color: #111613; }}
QPushButton#PrimaryButton {{
    color: #07110B;
    background-color: {ACCENT};
    border-color: {ACCENT};
    font-size: 15px;
    font-weight: 800;
}}
QPushButton#PrimaryButton:hover {{ background-color: #5BFFA0; border-color: #5BFFA0; }}
QPushButton#PreviewButton {{
    color: {ACCENT};
    border: 1px solid {ACCENT_DARK};
    background-color: #102219;
}}
QPushButton#CollapseButton {{
    min-height: 38px;
    text-align: left;
    color: {ACCENT};
    background-color: #102219;
    border-color: #285A3C;
}}
QPushButton#StopButton {{
    color: {ERROR};
    border-color: #71313B;
    background-color: #261519;
}}
QPushButton#StopButton:hover {{ background-color: #351A20; border-color: {ERROR}; }}
QPushButton#StopButton:disabled {{
    color: #66535A;
    border-color: #3A292E;
    background-color: #171113;
}}
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {{
    min-height: 42px;
    padding: 0 13px;
    border-radius: 11px;
    border: 1px solid #35483D;
    background-color: #0F1511;
    color: {TEXT};
    selection-background-color: {ACCENT_DARK};
}}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
    border-color: {ACCENT};
}}
QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled {{
    color: #647068;
    border-color: #27322B;
}}
QTableWidget {{
    color: {TEXT};
    background-color: #0F1511;
    alternate-background-color: #141C17;
    border: 1px solid #304137;
    border-radius: 10px;
    gridline-color: #29372F;
    selection-color: #07110B;
    selection-background-color: {ACCENT};
}}
QTableWidget::item {{
    padding: 7px;
}}
QTableWidget::item:focus {{
    border: 1px solid {ACCENT_DARK};
}}
QHeaderView::section {{
    color: {TEXT};
    background-color: {PANEL_ALT};
    border: 0;
    border-right: 1px solid #304137;
    border-bottom: 1px solid #304137;
    padding: 9px 7px;
    font-weight: 700;
}}
QComboBox::drop-down {{
    width: 34px;
    border: 0;
}}
QComboBox QAbstractItemView {{
    color: {TEXT};
    background-color: {PANEL_ALT};
    border: 1px solid #3A4D42;
    selection-color: #07110B;
    selection-background-color: {ACCENT};
    outline: 0;
}}
QSpinBox::up-button, QDoubleSpinBox::up-button,
QSpinBox::down-button, QDoubleSpinBox::down-button {{
    width: 22px;
    border: 0;
    background-color: #1E2B24;
}}
QSlider::groove:horizontal {{
    height: 7px;
    border-radius: 3px;
    background-color: #26332C;
}}
QSlider::sub-page:horizontal {{
    border-radius: 3px;
    background-color: {ACCENT_DARK};
}}
QSlider::handle:horizontal {{
    width: 18px;
    margin: -6px 0;
    border-radius: 9px;
    background-color: {ACCENT};
    border: 1px solid #8AFFB5;
}}
QTabWidget::pane {{
    border: 1px solid #29382F;
    border-radius: 13px;
    background-color: {BACKGROUND};
    top: -1px;
}}
QTabBar::tab {{
    min-width: 125px;
    min-height: 40px;
    padding: 0 18px;
    margin-right: 5px;
    border: 1px solid #2D3B33;
    border-bottom: 0;
    border-top-left-radius: 10px;
    border-top-right-radius: 10px;
    background-color: {PANEL};
    color: {MUTED};
    font-weight: 700;
}}
QTabBar::tab:selected {{
    color: {ACCENT};
    background-color: #102219;
    border-color: #2E6D48;
}}
QFrame#SettingsPanel, QGroupBox {{
    background-color: {PANEL};
    border: 1px solid #29382F;
    border-radius: 14px;
}}
QFrame#SettingsPanel QWidget, QGroupBox QWidget {{
    background-color: transparent;
}}
QGroupBox {{
    margin-top: 13px;
    padding: 15px 12px 12px 12px;
    font-weight: 700;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 14px;
    padding: 0 7px;
    color: {ACCENT};
    background-color: {BACKGROUND};
}}
QProgressBar {{
    min-height: 13px;
    max-height: 13px;
    border: 0;
    border-radius: 6px;
    background-color: #202923;
    text-align: center;
    color: transparent;
}}
QProgressBar::chunk {{
    border-radius: 6px;
    background-color: {ACCENT};
}}
QDialog, QMessageBox {{ background-color: {BACKGROUND}; }}
QDialog QLabel, QMessageBox QLabel {{ background-color: transparent; }}
QScrollArea, QScrollArea > QWidget > QWidget {{ border: 0; background-color: {BACKGROUND}; }}
QToolTip {{ color: {TEXT}; background-color: {PANEL_ALT}; border: 1px solid #3A4D42; }}
"""


def neon_shadow(widget: QWidget, *, blur: int = 28, strength: int = 130) -> None:
    effect = QGraphicsDropShadowEffect(widget)
    effect.setBlurRadius(blur)
    effect.setOffset(0, 0)
    effect.setColor(QColor(57, 255, 136, strength))
    widget.setGraphicsEffect(effect)
