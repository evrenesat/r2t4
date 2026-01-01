# R2T4 - TV Companion App

An Android app that turns an old phone/tablet into a "TV companion" to help a viewer get extra information and keep private, ephemeral notes about what they are watching.

## Features (MVP1)

- 🎤 **Continuous audio recording** - Captures ambient audio in 5-second chunks
- 📷 **Periodic camera capture** - Takes photos of the TV screen every 2 seconds
- 🗣️ **Wake word detection** - Say "Porcupine" to start a voice prompt (Picovoice)
- 📤 **Reliable upload** - Uploads to your private server with retry logic
- 🔒 **Privacy-first** - All data stays on your own infrastructure

## Project Structure

```
r2t4/
├── proto/           # Shared protobuf definitions (Connect-RPC)
├── server/          # Go server with admin web UI
├── android/         # Kotlin Android client
├── docs/            # Documentation
└── scripts/         # Build scripts
```

## Quick Start

### Prerequisites

- Go 1.22+
- Android Studio (for Android development)
- Buf CLI (`brew install bufbuild/buf/buf`)
- Picovoice account (for wake word detection)

### 1. Build and Run Server

```bash
# Generate proto code
./scripts/gen-proto.sh

# Run server (development)
cd server
go run ./cmd/r2t4-server --data-dir ./testdata

# Open admin UI
open http://localhost:8080
```

### 2. Build Android App

```bash
# Open in Android Studio
open android/

# Or build from command line
cd android
./gradlew assembleDebug

# Install on device
adb install -r app/build/outputs/apk/debug/app-debug.apk
```

### 3. Configure App

1. Open R2T4 app on your Android device
2. Go to Settings
3. Enter your server address (e.g., `http://192.168.1.100:8080`)
4. Enter a device ID (e.g., `living-room-tv`)
5. Optional: Enter your Picovoice access key for wake word detection

### 4. Start Capturing

1. Press "Start Capture" button
2. Point the device at your TV
3. Say "Porcupine" or press the mic button to ask questions
4. View responses in the log area

## Configuration

### Server Flags

```
--data-dir    Storage directory (default: ./data)
--listen      Listen address (default: :8080)
--tls-cert    TLS certificate file (optional)
--tls-key     TLS private key file (optional)
--config      JSON config file (optional)
```

### App Settings

| Setting              | Default                     | Description                     |
| -------------------- | --------------------------- | ------------------------------- |
| Server Address       | `http://192.168.1.100:8080` | R2T4 server URL                 |
| Device ID            | `my-tv-mate`                | Unique device identifier        |
| Audio Chunk Duration | 5 seconds                   | Duration of each audio chunk    |
| Photo Interval       | 2 seconds                   | Time between camera captures    |
| Photo Quality        | 70%                         | JPEG quality (10-100)           |
| Prompt Timeout       | 15 seconds                  | Max prompt recording time       |
| Push-to-Talk Mode    | Off                         | Use button instead of wake word |

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      Android Client                          │
├─────────────────────────────────────────────────────────────┤
│ ┌─────────────┐ ┌─────────────┐ ┌─────────────────────────┐ │
│ │   Audio     │ │   Camera    │ │      Wake Word          │ │
│ │  Recorder   │ │  Capturer   │ │  Detector (Porcupine)   │ │
│ └──────┬──────┘ └──────┬──────┘ └───────────┬─────────────┘ │
│        │               │                     │               │
│        ▼               ▼                     ▼               │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │                   Capture Service                       │ │
│ │  - Orchestrates all capture operations                  │ │
│ │  - Manages prompt recording                             │ │
│ └────────────────────────┬────────────────────────────────┘ │
│                          │                                   │
│                          ▼                                   │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │                   Upload Manager                        │ │
│ │  - Queue management                                     │ │
│ │  - Retry with exponential backoff                       │ │
│ │  - Backlog monitoring                                   │ │
│ └────────────────────────┬────────────────────────────────┘ │
│                          │                                   │
│                          ▼                                   │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │               R2T4 Client (Connect-RPC)                 │ │
│ └────────────────────────┬────────────────────────────────┘ │
└──────────────────────────┼──────────────────────────────────┘
                           │
                    ┌──────▼──────┐
                    │   Network   │
                    └──────┬──────┘
                           │
┌──────────────────────────┼──────────────────────────────────┐
│                          ▼                                   │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │              Go Server (Connect-RPC)                    │ │
│ └────────────────────────┬────────────────────────────────┘ │
│                          │                                   │
│         ┌────────────────┼────────────────┐                 │
│         ▼                ▼                ▼                 │
│ ┌──────────────┐ ┌──────────────┐ ┌──────────────────────┐ │
│ │   Upload     │ │   Prompt     │ │       Admin          │ │
│ │   Service    │ │   Service    │ │      Service         │ │
│ └──────┬───────┘ └──────┬───────┘ └──────────┬───────────┘ │
│        └────────────────┼────────────────────┘              │
│                         ▼                                    │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │                   File Storage                          │ │
│ │  /data/devices/<device_id>/                             │ │
│ │    ├── ambient/audio/<timestamp>_<seq>.wav              │ │
│ │    ├── ambient/images/<timestamp>.jpg                   │ │
│ │    └── prompts/<prompt_id>/audio.wav + response.json    │ │
│ └─────────────────────────────────────────────────────────┘ │
│                                                              │
│                       Go Server                              │
└──────────────────────────────────────────────────────────────┘
```

## API Reference

### gRPC Services (Connect-RPC)

- **UploadService**: `UploadAudioChunk`, `UploadImageFrame`
- **PromptService**: `SubmitPrompt` (streaming), `GetPromptResponse`, `CancelPrompt`
- **AdminService**: `GetHealth`, `ListDevices`, `ListFiles`, `ClearDevice`, `GetStats`

### REST Endpoints (Admin Web UI)

- `GET /api/health` - Server health check
- `GET /api/stats` - Storage statistics
- `GET /api/devices` - List all devices
- `GET /api/files?deviceId=...` - List files for device
- `GET /api/file/{deviceId}/{fileId}` - Download file
- `POST /api/clear/{deviceId}` - Clear device data

## Development

See [docs/setup.md](docs/setup.md) for development environment setup.
See [docs/building.md](docs/building.md) for build instructions.

## License

Private project - see LICENSE file.

## Roadmap

- **MVP1** (Current): Capture pipeline validation
- **MVP2**: Server-side speech-to-text, context processing
- **Future**: Custom wake words, multi-room support, iOS client
