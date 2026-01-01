# Building R2T4

Step-by-step build instructions for macOS (Apple Silicon M4).

## Quick Build (Both Server and Android)

```bash
# Generate proto code (required after proto changes)
./scripts/gen-proto.sh

# Build server
./scripts/build-server.sh

# Build Android (requires Android Studio setup)
./scripts/build-android.sh
```

Binaries will be in the `bin/` directory.

## Server Build

### Development (run directly)
```bash
cd server
go run ./cmd/r2t4-server --data-dir ./testdata
```

### Production binaries
```bash
./scripts/build-server.sh
```

This creates:
- `bin/r2t4-server-darwin-arm64` - macOS ARM64 (M4)
- `bin/r2t4-server-linux-amd64` - Linux x86_64
- `bin/r2t4-server-linux-arm64` - Linux ARM64 (Raspberry Pi)

### Running the server
```bash
# macOS
./bin/r2t4-server-darwin-arm64 --data-dir /path/to/storage

# Linux (copy to your server first)
scp bin/r2t4-server-linux-amd64 user@server:/opt/r2t4/
ssh user@server '/opt/r2t4/r2t4-server-linux-amd64 --data-dir /opt/r2t4/data'
```

### Server flags
```
--data-dir    Storage directory (default: ./data)
--listen      Listen address (default: :8080)
--tls-cert    TLS certificate file (optional)
--tls-key     TLS key file (optional)
```

## Android Build

### Prerequisites
- Android Studio installed
- Android SDK 34 (or latest)
- Java 17+ (bundled with Android Studio)

### Debug APK
```bash
cd android
./gradlew assembleDebug
```

APK location: `android/app/build/outputs/apk/debug/app-debug.apk`

### Release APK
```bash
cd android
./gradlew assembleRelease
```

> **Note:** Release builds require signing configuration. See Android documentation for setting up a keystore.

### Install on device via ADB
```bash
# List connected devices
adb devices

# Install debug APK
adb install -r android/app/build/outputs/apk/debug/app-debug.apk
```

### Using the build script
```bash
./scripts/build-android.sh          # Debug only
./scripts/build-android.sh --release # Both debug and release
```

## Updating Proto Definitions

After modifying any `.proto` file:

```bash
# Regenerate code
./scripts/gen-proto.sh

# Rebuild server
cd server && go build ./...

# In Android Studio, sync Gradle to regenerate Kotlin code
```

## Troubleshooting

### "buf: command not found"
```bash
brew install bufbuild/buf/buf
```

### "go: command not found"
```bash
brew install go
source ~/.zshrc
```

### Android build fails with SDK errors
Open Android Studio → Settings → Android SDK → Install missing SDK components

### Proto generation fails
```bash
# Check for lint errors
cd proto && buf lint

# Check for breaking changes (if applicable)
cd proto && buf breaking --against '.git#branch=main'
```
