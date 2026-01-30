# R2T4 Agent Guidelines & System Architecture

## Project Overview

R2T4 is a privacy-first TV Companion app that turns an old Android phone/tablet into an intelligent assistant for TV viewing. The device continuously captures ambient audio and periodic images of the TV screen, uploading them to a user-owned server. Users can ask questions about what they're watching using a wake word ("R2T4"), and the system uses captured context to provide relevant responses.

## Tech Stack

### Server (Go)
- **Language**: Go 1.22+
- **RPC Framework**: Connect-RPC (gRPC-compatible, browser-friendly)
- **Storage**: File-based (organized by device ID and timestamp)
- **Web UI**: Embedded HTML/CSS/JS served via Go embed
- **Protocol**: Connect-RPC over HTTP/2 (h2c for LAN, TLS optional)

### Android Client (Kotlin)
- **Language**: Kotlin
- **UI Framework**: Jetpack Compose
- **Architecture**: MVVM with coroutines and Flows
- **Camera**: CameraX
- **Audio**: MediaRecorder with PCM 16kHz mono
- **Wake Word**: Picovoice Porcupine (custom "R2T4" model)
- **Settings**: SQLite-backed repository
- **Network**: Connect-RPC Kotlin client

### Protocol (Protobuf)
- **Location**: `proto/r2t4/v1/`
- **Services**: UploadService, PromptService, AdminService
- **Code Generation**: Buf CLI → Go + Kotlin

## Architecture

### High-Level Flow
```
TV Screen → Camera → ImageCapturer → UploadManager → Server Storage
TV Audio → Mic → AudioRecorder → UploadManager → Server Storage
                     ↓
              WakeWordDetector
                     ↓ (on "R2T4")
              PromptRecorder
                     ↓
              UploadManager (priority)
                     ↓
              Server PromptService
                     ↓
              Response → UI
```

### Key Components (Agents)

Detailed component descriptions are available in the full documentation. Key agents:

1. **CaptureService** (orchestrator) - Coordinates all capture operations
2. **AudioRecorder** - Continuous 16kHz audio capture with dual outputs (chunks + frames)
3. **WakeWordDetector** - On-device Porcupine-based wake word detection
4. **PromptRecorder** - Captures user prompts with VAD-based endpoint detection
5. **ImageCapturer** - Periodic CameraX-based photo capture
6. **UploadManager** - Queue management with retry logic and backlog protection
7. **R2T4Client** - Connect-RPC client for server communication

See detailed agent descriptions in separate documentation or code comments.

### Directory Structure
```
r2t4/
├── proto/              # Shared protobuf definitions (Connect-RPC)
│   └── r2t4/v1/       # Service definitions (upload, prompt, admin)
├── server/            # Go server
│   ├── cmd/           # Main entry point
│   ├── internal/      # Handler, storage, config, web
│   └── gen/           # Generated protobuf code
├── android/           # Kotlin Android client
│   └── app/src/main/java/com/r2t4/app/
│       ├── audio/     # AudioRecorder, WakeWordDetector, PromptRecorder
│       ├── camera/    # ImageCapturer
│       ├── service/   # CaptureService, UploadManager
│       ├── grpc/      # R2T4Client
│       ├── settings/  # SettingsRepository
│       └── ui/        # Compose UI (MainScreen, SettingsScreen)
├── docs/              # Documentation
└── scripts/           # Build scripts (gen-proto.sh)
```

## Conventions

### Code Style

#### Go
- Standard `gofmt` formatting
- Use structured logging (log.Printf with context)
- Error wrapping with context: `fmt.Errorf("context: %w", err)`
- Short variable names for local scope, descriptive for package-level

#### Kotlin
- Follow Android Kotlin style guide
- Use coroutines for async operations
- Expose state via StateFlow/SharedFlow for observability
- Explicit resource cleanup (release/close in finally or use blocks)
- Type safety preferred over Any/unchecked casts

### Git
- **Commit format**: `type: description` or `type(scope): description`
  - Types: feat, fix, refactor, docs, test
  - Example: `feat: allow microphone selection`
  - Example: `fix: camera aspect ratio bug`
- Keep commits focused (single logical change)
- Update DEVLOG.md with significant changes

### Testing
- **MVP1 Status**: Manual testing only
- **MVP2+**: Add unit tests for core logic, integration tests for RPC
- Test on real hardware (Moto Z Play, Android 8+)
- Validate 8-hour reliability runs (<1% chunk loss)

### Protocol Changes
When modifying protobuf definitions:
1. Edit `.proto` files in `proto/r2t4/v1/`
2. Run `./scripts/gen-proto.sh` to regenerate code
3. Update both client and server handlers
4. Test RPC calls end-to-end

## Before Starting Work

1. **Read DEVLOG.md** - Understand recent changes and current issues
2. **Check project status** - Are there known blockers or in-progress tasks?
3. **Review related code** - Understand how components interact
4. **Read questions_answers.md** - Understand design decisions and constraints

## After Completing Work

1. **Update DEVLOG.md** with:
   - Date and summary
   - What was changed and why
   - Files modified
   - Any gotchas or follow-up work needed
2. **Update documentation** if architecture/behavior changed
3. **Test on device** - Don't just compile, verify it works
4. **Commit with clear message** - Follow conventional commit format

## Known Gotchas

### Android
- **Porcupine frame size**: Must be exactly 512 samples (16ms at 16kHz)
- **AudioRecord buffer timing**: Reads must align with wake word frame processing
- **CameraX aspect ratios**: Set explicit aspect ratio to avoid distortion
- **Foreground service**: Required for reliable background operation
- **Permission checks**: Camera/mic permissions must be checked before initialization
- **WAV encoding**: Prompt audio needs proper WAV headers for server compatibility

### Go
- **h2c handler**: Required for Connect-RPC without TLS
- **File writes**: Use atomic write (temp + rename) to avoid partial files
- **Path traversal**: Sanitize file paths in API endpoints (check prefix)
- **CORS**: Not needed for Connect-RPC (uses POST with protobuf)

### Protocol
- **Timestamps**: Client wall-clock used, assumes NTP sync
- **Chunk sequencing**: Audio chunks have sequence numbers for ordering
- **Backlog limits**: Client enforces 2-minute max backlog before shutdown

### Settings
- **SQLite persistence**: Settings survive app updates
- **Server address validation**: Client doesn't validate URL format (user responsibility)
- **Porcupine key**: Must be obtained from Picovoice Console

## Key Files

| File | Purpose |
|------|---------|
| `android/app/.../service/CaptureService.kt` | Main orchestrator, lifecycle management |
| `android/app/.../service/UploadManager.kt` | Queue management, retry logic |
| `android/app/.../audio/WakeWordDetector.kt` | Porcupine integration |
| `android/app/.../audio/PromptRecorder.kt` | Prompt capture with VAD |
| `android/app/.../grpc/R2T4Client.kt` | Connect-RPC client implementation |
| `server/cmd/r2t4-server/main.go` | Server entry point, HTTP setup |
| `server/internal/handler/*.go` | RPC service implementations |
| `server/internal/storage/storage.go` | File storage management |
| `proto/r2t4/v1/*.proto` | Service definitions |

## Development Workflow

### Building

**Server**:
```bash
cd server
go build -o r2t4-server ./cmd/r2t4-server
./r2t4-server --data-dir ./data --listen :8080
```

**Android** (from project root):
```bash
cd android
./gradlew assembleDebug
adb install -r app/build/outputs/apk/debug/app-debug.apk
```

**Proto regeneration**:
```bash
./scripts/gen-proto.sh
```

### Running

1. Start server: `./r2t4-server --data-dir ./data`
2. Open admin UI: `http://localhost:8080`
3. Install app on Android device
4. Configure settings (server address, device ID, Porcupine key)
5. Start capture

### Debugging

**Server logs**: stdout (structured format)
**Client logs**: Android Logcat (`adb logcat | grep R2T4`)
**UI logs**: In-app scrolling log view
**Admin UI**: Browse uploaded files, check stats

## Current Status (MVP1)

### ✅ Completed
- Continuous audio capture (5s chunks)
- Periodic image capture (2s intervals)
- Custom wake word detection ("R2T4")
- Prompt recording with VAD
- Upload with retry and backlog management
- Server storage and admin web UI
- Settings management
- Microphone source selection

### 🚧 Known Limitations
- No speech-to-text processing (placeholder responses only)
- No image understanding
- No background/screen-off operation
- No multi-device coordination
- No authentication (LAN-only)

### 🔜 MVP2 Planned
- Continuous speech-to-text on ambient audio
- Image scene classification
- Context-aware LLM responses
- Server-side wake word option
- Voice identification
- Remote server with TLS

## Agent Best Practices

When working with this codebase:

1. **Respect the agent architecture** - Each component has a single responsibility
2. **Use coroutines correctly** - Don't block, use suspend functions
3. **Handle failures gracefully** - Degrade functionality rather than crash
4. **Maintain observability** - Emit status via Flows, log appropriately
5. **Test on real hardware** - Emulator behavior differs significantly
6. **Consider power/performance** - This runs for hours on old devices
7. **Privacy first** - All data stays on user's infrastructure

## References

- **Setup Guide**: `docs/setup.md`
- **Build Instructions**: `docs/building.md`
- **Design Q&A**: `questions_answers.md`
- **Architecture Overview**: `readme.md`
- **Change History**: `DEVLOG.md`
