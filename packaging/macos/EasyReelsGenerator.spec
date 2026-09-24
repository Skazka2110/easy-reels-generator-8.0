import os
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files


repo_root = Path(SPECPATH).resolve().parents[1]
icon_path = repo_root / "packaging" / "macos" / "easy-reels.icns"
ffmpeg_path = Path(os.environ["EASY_REELS_FFMPEG"]).resolve()
ffprobe_path = Path(os.environ["EASY_REELS_FFPROBE"]).resolve()

analysis = Analysis(
    [str(repo_root / "packaging" / "macos" / "launcher.py")],
    pathex=[str(repo_root / "src")],
    binaries=[
        (str(ffmpeg_path), "."),
        (str(ffprobe_path), "."),
    ],
    datas=collect_data_files("easy_reels"),
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=1,
)

pyz = PYZ(analysis.pure)

exe = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="Easy Reels Generator",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

bundle_files = COLLECT(
    exe,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="Easy Reels Generator",
)

app = BUNDLE(
    bundle_files,
    name="Easy Reels Generator.app",
    icon=str(icon_path),
    bundle_identifier="pw.proaistudio.easy-reels-generator",
    info_plist={
        "CFBundleDisplayName": "Easy Reels Generator",
        "CFBundleShortVersionString": "0.8.0",
        "CFBundleVersion": "0.8.0",
        "NSHighResolutionCapable": True,
    },
)
