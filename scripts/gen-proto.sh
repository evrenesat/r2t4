#!/bin/bash
# Generate Go and Kotlin code from proto definitions
# Run from the project root directory

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "==> Generating Go code from proto definitions..."
cd "$PROJECT_ROOT/proto"
buf generate

echo "==> Go code generated successfully in server/gen/"

# TODO: Add Kotlin generation when Android project is set up
# This will be done via Gradle plugin in the Android project

echo "==> Done!"
