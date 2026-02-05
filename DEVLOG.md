# R2T4 Development Log

> Tracks the evolution of the R2T4 TV Companion project.

## Current State
- **Last Updated:** 2026-02-05
- **Status:** MVP1 Complete - Active Development
- **In Progress:** Documentation updates (AGENTS.md, DEVLOG.md)
- **Recently Completed:** End-to-end capture/upload pipeline with custom "R2T4" wake word, mic selection, and VAD-based prompt recording.

---

## Session Log

### 2026-02-05: Architecture Documentation Restructure
- **Goal:** Replace stale/sparse architecture notes with an implementation-accurate system reference before adding new features.
- **Changes:**
  - Rewrote `ARCHITECTURE.md` to reflect current Android and Go server behavior end-to-end.
  - Added explicit runtime topology, component boundaries, and data flow for:
    - `CaptureService`, `AudioRecorder`, `PromptRecorder`, `WakeWordDetector`, `ImageCapturer`, `UploadManager`, and `R2T4Client`.
    - Server handler wiring (`UploadService`, `PromptService`, `AdminService`, `PluginService`) and plugin execution model.
  - Documented actual storage contract under `data/devices/<device_id>/...`.
  - Added sections for reliability/failure behavior, security posture, known technical debt, and primary entry files.
- **Why:** Upcoming feature work needs a precise architecture baseline; previous doc had drift (for example around settings storage and transport details).
- **Verification:**
  - `GOCACHE=/tmp/r2t4-go-cache go test ./...` (passes; no test files present).
  - Android `./gradlew test` could not complete in sandbox due Gradle distribution download restriction (`UnknownHostException: services.gradle.org`).
- **Follow-up:**
  - Add automated tests (Go/Kotlin coverage is still missing).
  - Re-run Android tests when Gradle is available offline or network is enabled.

### 2026-01-30: Plugin System Implementation
- **Goal:** Enable modular processing (subtitles, IMDB, etc.) without bloating the core.
- **Approach:** Spawn-and-exit CGI-style model using JSON over stdin/stdout (`--execute`) and `--handshake` for registration.
- **Components:** `PluginService` (proto), management in `manager.go`, interactive logs in Web UI.
- **Next:** Sample Python plugin, resource limits, and sidecar support for real-time audio.

### 2026-01-02: Core Refinements & Fixes
- **Wake Word:** Switched to custom "R2T4" model via Picovoice; implemented runtime model extraction for Android.
- **Mic Selection:** Added `UNPROCESSED` source option to bypass system AGC/noise suppression, significantly improving wake word accuracy.
- **Camera:** Fixed 16:9 aspect ratio distortion in `ImageCapturer.kt`.
- **Audio Reliability:**
    - Fixed silent chunks by validating `AudioRecord` buffer before emission.
    - Fixed empty prompts by implementing proper WAV header generation in `R2T4Client.kt`.
    - Added priority retry logic for prompts (high-speed backlog processing).

### 2026-01-01: MVP1 Initial Launch
- **Goal:** Validate continuous capture/upload pipeline reliability on older hardware (Moto Z Play).
- **Architecture:** Go server (Connect-RPC, file-based storage) + Kotlin client (Foreground Service, CameraX, Porcupine).
- **Result:** Successfully demonstrated 8+ hour continuous operation with <1% chunk loss over LAN.

---

## MVP1 Retrospective
- **Effort:** ~5,300 LOC (2k Go, 3k Kotlin), 2 days, 9 commits.
- **Hardware:** Moto Z Play 2016 (Android 8, SD625) - Target met.
- **Stack:** Go + Connect-RPC and Kotlin + Coroutines proved highly efficient. CameraX and Porcupine had quirks but are solid for MVP.
- **Lessons:** 
    - Real hardware testing is essential (caught WAV/Mic issues early).
    - Proto-first design enabled fast parallel development.
    - WAV encoding and audio buffer alignment were the primary technical hurdles.

---

## Roadmap: MVP2
- **Context Processing:** Continuous STT (Whisper), Image understanding (CLIP), and sliding context windows.
- **Intelligence:** LLM integration, RAG over captured context, and conversation history.
- **Infrastructure:** Remote server support (TLS), multi-device coordination, and data retention policies.
- **Challenges:** Resource-intensive compute, latency goals, and storage growth management.

---

## References
- **Design:** [ARCHITECTURE.md](ARCHITECTURE.md), [questions_answers.md](questions_answers.md)
- **Guides:** [docs/setup.md](docs/setup.md), [docs/building.md](docs/building.md)
- **Client Agent:** [AGENTS.md](AGENTS.md)
- **Main:** [README.md](README.md)
