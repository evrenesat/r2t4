# Development Environment Setup

This guide covers setting up the development environment for R2T4 on macOS (Apple Silicon).

## Prerequisites

### Homebrew (if not already installed)
```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

### Go 1.22+
```bash
brew install go
go version  # Should show 1.22 or higher
```

### Buf CLI (for Protocol Buffers)
```bash
brew install bufbuild/buf/buf
buf --version
```

### Android Studio
1. Download from https://developer.android.com/studio
2. Install and open Android Studio
3. Go to **Settings → Languages & Frameworks → Android SDK**
4. Install SDK Platform: **Android 14 (API 34)** (or latest)
5. Install SDK Tools:
   - Android SDK Build-Tools
   - Android SDK Command-line Tools
   - Android SDK Platform-Tools

### Environment Variables
Add to your `~/.zshrc`:
```bash
export ANDROID_HOME="$HOME/Library/Android/sdk"
export PATH="$PATH:$ANDROID_HOME/platform-tools"
export PATH="$PATH:$ANDROID_HOME/cmdline-tools/latest/bin"
```

Then reload: `source ~/.zshrc`

## Picovoice Account (for Wake Word Detection)

1. Create account at https://console.picovoice.ai/
2. Get your Access Key from the dashboard
3. You'll configure this in the Android app settings

## Project Setup

### Clone and setup
```bash
git clone <repo-url>
cd r2t4
```

### Generate proto code
```bash
./scripts/gen-proto.sh
```

### Verify Go setup
```bash
cd server
go mod download
go build ./...
```

### Verify Android setup
```bash
cd android
./gradlew build
```

## IDE Setup

### For Go (VS Code recommended)
1. Install VS Code
2. Install "Go" extension by Google
3. Open `server/` folder

### For Android (Android Studio required)
1. Open `android/` folder in Android Studio
2. Wait for Gradle sync to complete
3. Connect your test device or start an emulator

## Next Steps

- See [building.md](building.md) for build instructions
- See [api.md](api.md) for API documentation
