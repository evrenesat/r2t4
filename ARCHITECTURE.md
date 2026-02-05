# R2T4 Architecture

This document describes the architecture currently implemented in the repository. It is the operational reference for how the Android client and Go server actually behave today.

## 1. System Purpose and Scope

R2T4 turns an Android device into a long-running TV companion sensor and prompt endpoint:

- Ambient capture:
  - Continuous microphone capture (chunked WAV uploads).
  - Periodic camera snapshots (JPEG uploads).
- Prompt interaction:
  - Wake word ("R2T4") or push-to-talk starts prompt recording.
  - Prompt audio uploads to server for asynchronous processing.
- Admin surface:
  - Server exposes Connect-RPC APIs and a built-in web dashboard.
  - Optional plugin subsystem managed from the server/admin UI.

Current maturity is MVP1: ingestion, storage, and orchestration are implemented; semantic understanding and real responses are not.

## 2. Runtime Topology

```
Android Device
  MainActivity (Compose UI)
       |
       v
  CaptureService (foreground orchestrator)
     |- AudioRecorder ---------\
     |- WakeWordDetector        +--> UploadManager --> R2T4Client --> Go Server
     |- PromptRecorder --------/
     |- ImageCapturer --------/

Go Server (single binary)
  - UploadService (audio/image ingest)
  - PromptService (queue + placeholder processing)
  - AdminService (device/files/stats)
  - PluginService (plugin registry/control)
  - REST admin endpoints + static web UI
  - File-based storage under data/devices/
```

## 3. Repository Layout

```
r2t4/
  android/                  Android app (Kotlin, Compose, CameraX, coroutines)
  server/                   Go server (Connect-RPC + REST + embedded web UI)
  proto/r2t4/v1/            Service contracts (upload, prompt, admin, plugin)
  server/gen/               Generated Go protobuf/connect code
  scripts/                  Build/proto generation scripts
  docs/                     Setup/build docs
```

## 4. Android Client Architecture

### 4.1 Entry and UI Layer

- `MainActivity` requests permissions, hosts Compose navigation, and dispatches service actions.
- UI screens:
  - `MainScreen`: run state, logs, upload counters, controls (start/stop/push-to-talk/done/cancel).
  - `SettingsScreen`: edits persisted capture/network settings.
- App-level setup:
  - `R2T4Application` creates notification channel for foreground service.

### 4.2 Orchestration Layer

`CaptureService` is the core runtime coordinator.

Responsibilities:
- Starts as a foreground service (`START_STICKY`).
- Loads settings once at startup from `SettingsRepository`.
- Initializes:
  - `R2T4Client`
  - `UploadManager`
  - `AudioRecorder`
  - `WakeWordDetector` (if enabled and access key present)
  - `ImageCapturer` (if camera permission/hardware/init succeed)
  - `PromptRecorder`
- Collects flows:
  - Audio chunks -> upload queue (unless prompt is recording).
  - Audio frames -> wake word processing and prompt recorder input.
  - Image frames -> upload queue.
  - Prompt completion -> prompt upload + response poll.
  - Upload status -> UI stats and backlog failure handling.

Service state is exposed via a singleton `StateFlow<CaptureState>`.

### 4.3 Capture Components

`AudioRecorder`
- Uses `AudioRecord`, 16 kHz mono PCM16.
- Emits:
  - `audioFrames`: short frames for wake-word/prompt processing.
  - `audioChunks`: WAV chunks for ambient upload.
- Configurable `chunkDurationSeconds` (default 5s).
- Uses frame size 512 samples.

`WakeWordDetector`
- Picovoice Porcupine integration.
- Extracts custom model `r_two_t_four.ppn` from app resources into app files dir.
- Processes incoming frames; emits detection timestamps.
- If init fails, system remains operational in push-to-talk mode.

`PromptRecorder`
- Reuses audio frames from `AudioRecorder`; no separate recorder.
- Energy-based VAD with timeout.
- End reasons: user done, user cancel, silence, timeout.
- Emits `PromptResult` containing WAV payload and timing metadata.

`ImageCapturer`
- CameraX `ImageCapture`, back camera, no preview use-case.
- Periodic capture loop using coroutine delay.
- Converts captured image data to JPEG, rotates, and downscales to configured bounds.

### 4.4 Upload and Network

`UploadManager`
- Three internal buffered channels:
  - audio chunks
  - image frames
  - full prompts
- Runs one worker coroutine per channel.
- Retry model:
  - Audio/image: max 3 retries, exponential delay from 1000 ms base.
  - Prompt: up to 6 retries, 500 ms delay.
- Backlog control:
  - Ambient uploads are rejected when backlog age exceeds 120 seconds.
  - Backlog exceeded flag is surfaced; `CaptureService` stops capture when seen.

`R2T4Client`
- Uses OkHttp directly.
- Upload audio/image via JSON POST to Connect paths:
  - `/r2t4.v1.UploadService/UploadAudioChunk`
  - `/r2t4.v1.UploadService/UploadImageFrame`
- Prompt submit uses Connect streaming framing manually over `application/connect+json` to:
  - `/r2t4.v1.PromptService/SubmitPrompt`
- `GetPromptResponse` currently returns a client-side placeholder on successful HTTP response.

### 4.5 Settings and Persistence

`SettingsRepository` uses Android DataStore Preferences (not SQLite).

Stored values include:
- server address
- device ID
- audio chunk duration
- photo interval
- photo quality
- prompt timeout
- push-to-talk mode
- Porcupine access key
- microphone source

## 5. Server Architecture (Go)

### 5.1 Process and Transport

`cmd/r2t4-server/main.go`:
- Loads config from defaults + optional JSON + CLI flags.
- Initializes storage and handlers.
- Registers Connect services:
  - UploadService
  - PromptService
  - AdminService
  - PluginService
- Registers REST-style admin endpoints used by web UI.
- Serves embedded static web assets.
- Runs HTTP server with h2c for HTTP/2 cleartext (TLS optional).
- Includes unary Connect logging interceptor.

### 5.2 Service Handlers

`UploadHandler`
- Validates audio/image upload payloads.
- Persists files via storage layer.
- Returns ack IDs and server timestamps.

`PromptHandler`
- Accepts client-streaming prompt audio.
- Stores prompt audio to disk.
- Enqueues prompt state in an in-memory FIFO queue.
- Background worker (`processQueue`) creates MVP1 placeholder response.
- Persists response JSON in prompt folder.
- Supports polling (`GetPromptResponse`) and queue cancellation.

`AdminHandler`
- Implements health, list devices, list files, clear device, stats.
- `GetFile` and `DeleteFiles` Connect methods are currently unimplemented/simplified.
- Equivalent functionality for web UI is provided through REST endpoints in `main.go`.

`PluginHandler`
- Exposes plugin manager operations: list/register/unregister/enable-disable/test.

### 5.3 Plugin Subsystem

`internal/plugin/manager.go`
- Persists registry in `<data_dir>/plugins.json`.
- Validates executable path.
- Handshake-based metadata discovery before registration.

`internal/plugin/executor.go`
- Spawn-and-exit execution model.
- Handshake: plugin invoked with `--handshake`.
- Execute: plugin invoked with `--execute`, request passed via stdin JSON.
- Default execution timeout: 60 seconds.

`internal/plugin/logger.go`
- Appends interaction log lines to `<data_dir>/plugin_logs.txt`.
- Provides bounded readback for admin UI.

### 5.4 Storage Layer

`internal/storage/storage.go` provides mutex-protected file storage.

Directory contract:

```
<data_dir>/
  devices/
    <device_id>/
      ambient/
        audio/<timestamp_ms>_<seq>.wav
        images/<timestamp_ms>.jpg
      prompts/
        <prompt_id>/
          audio.wav
          response.json
```

Capabilities:
- Save audio/image/prompt artifacts.
- List devices and aggregate stats.
- List files with pagination/filtering.
- Clear all files for one device.
- Path-prefix checks for file access safety.

## 6. Protocol Layer (Protobuf)

Source files under `proto/r2t4/v1/` define:
- `UploadService`
- `PromptService`
- `AdminService`
- `PluginService`
- Shared message types in `common.proto`

Code generation:
- Go code committed under `server/gen`.
- Kotlin protobuf usage is partial in current Android client (manual JSON/connect calls are used for network operations).

## 7. End-to-End Flows

### 7.1 Service Start

1. User presses start in UI.
2. `MainActivity` sends `ACTION_START` to `CaptureService`.
3. Service enters foreground and loads settings.
4. Upload manager + capture components initialize.
5. Ambient audio/camera pipelines begin and feed upload queues.

### 7.2 Ambient Ingestion

1. `AudioRecorder` emits WAV chunks and frame stream.
2. `ImageCapturer` emits JPEG frames at configured interval.
3. `UploadManager` retries upload failures per queue policy.
4. Server `UploadService` persists each artifact to device folder.

### 7.3 Prompt Interaction

1. Wake word hit or push-to-talk triggers `PromptRecorder.start`.
2. Prompt recorder accumulates frames until silence, timeout, done, or cancel.
3. Completed prompt is queued with upload priority.
4. Server stores prompt and places it in prompt queue.
5. Background processor marks completed and writes placeholder response.
6. Client polls `GetPromptResponse` and displays text in log view.

### 7.4 Admin and Files

1. Browser opens server root (`/`) for embedded dashboard.
2. Dashboard calls REST endpoints (`/api/health`, `/api/stats`, `/api/devices`, `/api/files`, `/api/file/...`, `/api/clear/...`, plugin APIs).
3. Server translates calls to storage/plugin operations and returns JSON.

## 8. Reliability and Failure Behavior

- Android component failures degrade selectively:
  - Camera init failure disables only camera capture.
  - Wake word init failure falls back to push-to-talk.
- Upload retry and queue separation prevent prompt starvation by ambient traffic.
- Backlog age guard prevents unbounded ambient queue growth.
- Server shutdown is graceful (10s timeout) on SIGINT/SIGTERM.
- No persistent local queue on Android yet; dropped ambient items are not recovered after overflow.

## 9. Security and Privacy Posture

- Privacy goal: user-owned infrastructure, local storage by default.
- Current security model is MVP1/LAN-oriented:
  - no authn/authz
  - optional TLS
  - cleartext traffic allowed on Android
- File-serving endpoint includes path-prefix checks to reduce traversal risk.

## 10. Known Gaps and Technical Debt

- No automated unit/integration test coverage in repository today.
- Prompt responses are placeholder only (no STT/LLM pipeline yet).
- Android `GetPromptResponse` path currently returns a local placeholder on HTTP success.
- Connect `AdminService` has unimplemented methods for file retrieval/deletion.
- Storage writes are direct `os.WriteFile` (no atomic temp-rename pattern yet).
- Backlog handling drops new ambient data when exceeded; no disk-backed local spool.

## 11. Primary Files to Read First

- Android orchestration:
  - `android/app/src/main/java/com/r2t4/app/service/CaptureService.kt`
  - `android/app/src/main/java/com/r2t4/app/service/UploadManager.kt`
- Android capture/network:
  - `android/app/src/main/java/com/r2t4/app/audio/AudioRecorder.kt`
  - `android/app/src/main/java/com/r2t4/app/audio/PromptRecorder.kt`
  - `android/app/src/main/java/com/r2t4/app/audio/WakeWordDetector.kt`
  - `android/app/src/main/java/com/r2t4/app/camera/ImageCapturer.kt`
  - `android/app/src/main/java/com/r2t4/app/grpc/R2T4Client.kt`
- Server:
  - `server/cmd/r2t4-server/main.go`
  - `server/internal/handler/upload.go`
  - `server/internal/handler/prompt.go`
  - `server/internal/handler/admin.go`
  - `server/internal/handler/plugin.go`
  - `server/internal/storage/storage.go`
  - `server/internal/plugin/manager.go`

## 12. Documentation Update Rule

When behavior changes in orchestration, network contracts, storage layout, or plugin execution model, update this file in the same change set as code.
