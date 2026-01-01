#!/bin/bash
# Build the R2T4 Android app
# Run from the project root directory

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ANDROID_DIR="$PROJECT_ROOT/android"
BIN_DIR="$PROJECT_ROOT/bin"

# Create bin directory
mkdir -p "$BIN_DIR"

cd "$ANDROID_DIR"

echo "==> Building R2T4 Android app..."

# Build debug APK
echo "==> Building debug APK..."
./gradlew assembleDebug

# Copy APK to bin directory
DEBUG_APK=$(find app/build/outputs/apk/debug -name "*.apk" | head -1)
if [ -n "$DEBUG_APK" ]; then
    cp "$DEBUG_APK" "$BIN_DIR/r2t4-debug.apk"
    echo "==> Debug APK: $BIN_DIR/r2t4-debug.apk"
fi

# Optionally build release APK (requires signing config)
if [ "$1" == "--release" ]; then
    echo "==> Building release APK..."
    ./gradlew assembleRelease
    RELEASE_APK=$(find app/build/outputs/apk/release -name "*.apk" | head -1)
    if [ -n "$RELEASE_APK" ]; then
        cp "$RELEASE_APK" "$BIN_DIR/r2t4-release.apk"
        echo "==> Release APK: $BIN_DIR/r2t4-release.apk"
    fi
fi

echo ""
echo "==> Build complete!"
