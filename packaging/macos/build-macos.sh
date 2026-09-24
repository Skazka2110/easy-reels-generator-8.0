#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$ROOT"

if [[ "$(uname -s)" != "Darwin" ]]; then
    echo "This build script must run on macOS."
    exit 1
fi

ARCH="$(uname -m)"
case "$ARCH" in
    arm64) BUILD_LABEL="ARM64" ;;
    x86_64) BUILD_LABEL="Intel" ;;
    *) echo "Unsupported architecture: $ARCH"; exit 1 ;;
esac

PYTHON_BIN="${PYTHON_BIN:-python3}"
VENV="$ROOT/.macos-build-venv-$ARCH"
VENV_PYTHON="$VENV/bin/python"

if [[ ! -x "$VENV_PYTHON" ]]; then
    "$PYTHON_BIN" -m venv "$VENV"
fi

"$VENV_PYTHON" -m pip install --upgrade pip
"$VENV_PYTHON" -m pip install --upgrade \
    -r "$ROOT/packaging/windows/requirements-build.txt" \
    "$ROOT"

if ! command -v ffmpeg >/dev/null 2>&1 || ! command -v ffprobe >/dev/null 2>&1; then
    if ! command -v brew >/dev/null 2>&1; then
        echo "FFmpeg is missing and Homebrew is not installed."
        exit 1
    fi
    brew install ffmpeg
fi

ICONSET="$ROOT/build/macos/easy-reels.iconset"
ICON_PNG="$ROOT/src/easy_reels/assets/icon.png"
ICON_OUT="$ROOT/packaging/macos/easy-reels.icns"
rm -rf "$ICONSET"
mkdir -p "$ICONSET"
for SIZE in 16 32 128 256 512; do
    DOUBLE=$((SIZE * 2))
    sips -z "$SIZE" "$SIZE" "$ICON_PNG" --out "$ICONSET/icon_${SIZE}x${SIZE}.png" >/dev/null
    sips -z "$DOUBLE" "$DOUBLE" "$ICON_PNG" --out "$ICONSET/icon_${SIZE}x${SIZE}@2x.png" >/dev/null
done
iconutil -c icns "$ICONSET" -o "$ICON_OUT"

BUILD_ROOT="$ROOT/build/macos/$ARCH"
DIST_ROOT="$ROOT/artifacts/macos/dist-$ARCH"
PACKAGE_ROOT="$ROOT/artifacts/macos/Easy Reels Generator macOS $BUILD_LABEL"
ZIP_PATH="$ROOT/artifacts/macos/Easy_Reels_Generator_macOS_${BUILD_LABEL}_v080.zip"
rm -rf "$BUILD_ROOT" "$DIST_ROOT" "$PACKAGE_ROOT" "$ZIP_PATH"
mkdir -p "$BUILD_ROOT" "$DIST_ROOT" "$PACKAGE_ROOT"

export EASY_REELS_FFMPEG="$(command -v ffmpeg)"
export EASY_REELS_FFPROBE="$(command -v ffprobe)"

"$VENV_PYTHON" -m PyInstaller \
    --noconfirm \
    --clean \
    --workpath "$BUILD_ROOT" \
    --distpath "$DIST_ROOT" \
    "$ROOT/packaging/macos/EasyReelsGenerator.spec"

APP_PATH="$DIST_ROOT/Easy Reels Generator.app"
if [[ ! -d "$APP_PATH" ]]; then
    echo "PyInstaller did not create the expected .app bundle."
    exit 1
fi

codesign --force --deep --sign - "$APP_PATH"
cp -R "$APP_PATH" "$PACKAGE_ROOT/"
cp -R "$ROOT/portable_template/." "$PACKAGE_ROOT/"
mkdir -p \
    "$PACKAGE_ROOT/videos/top" \
    "$PACKAGE_ROOT/videos/bottom" \
    "$PACKAGE_ROOT/music" \
    "$PACKAGE_ROOT/ready" \
    "$PACKAGE_ROOT/preview" \
    "$PACKAGE_ROOT/logs" \
    "$PACKAGE_ROOT/backups" \
    "$PACKAGE_ROOT/licenses"

ditto -c -k --sequesterRsrc --keepParent "$PACKAGE_ROOT" "$ZIP_PATH"
echo "Build completed: $ZIP_PATH"
