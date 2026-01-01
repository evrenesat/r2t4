#!/bin/bash
# Build the R2T4 server for macOS (M4) and Linux
# Run from the project root directory

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SERVER_DIR="$PROJECT_ROOT/server"
BIN_DIR="$PROJECT_ROOT/bin"

# Create bin directory
mkdir -p "$BIN_DIR"

cd "$SERVER_DIR"

# Get version from git or use "dev"
VERSION="${VERSION:-$(git describe --tags --always --dirty 2>/dev/null || echo "dev")}"
BUILD_TIME=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

LDFLAGS="-X main.Version=$VERSION -X main.BuildTime=$BUILD_TIME"

echo "==> Building R2T4 server version $VERSION..."

# Build for macOS ARM64 (M4)
echo "==> Building for macOS ARM64..."
GOOS=darwin GOARCH=arm64 go build -ldflags "$LDFLAGS" -o "$BIN_DIR/r2t4-server-darwin-arm64" ./cmd/r2t4-server

# Build for Linux AMD64
echo "==> Building for Linux AMD64..."
GOOS=linux GOARCH=amd64 go build -ldflags "$LDFLAGS" -o "$BIN_DIR/r2t4-server-linux-amd64" ./cmd/r2t4-server

# Build for Linux ARM64 (e.g., Raspberry Pi 4)
echo "==> Building for Linux ARM64..."
GOOS=linux GOARCH=arm64 go build -ldflags "$LDFLAGS" -o "$BIN_DIR/r2t4-server-linux-arm64" ./cmd/r2t4-server

echo ""
echo "==> Build complete! Binaries in $BIN_DIR:"
ls -la "$BIN_DIR"
