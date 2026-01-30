# R2T4 Development Log

> This file tracks the evolution of the R2T4 TV Companion project. Update after significant changes.

## Current State
**Last Updated:** 2026-01-30
**Status:** MVP1 Complete - Active Development

### In Progress
- [ ] Documentation updates (AGENTS.md, DEVLOG.md)

### Recently Completed
- [x] MVP1: Full capture and upload pipeline
- [x] Custom wake word "R2T4" integration
- [x] Microphone source selection
- [x] Camera aspect ratio fixes
- [x] Prompt recording with VAD
- [x] Upload retry with backlog management

### Blocked / On Hold
- [ ] MVP2: Speech-to-text processing - Waiting on server capacity planning
- [ ] iOS client - After MVP2 validation

---

## Session Log

### 2026-01-02 - Custom Wake Word Integration

**Context:** The default Porcupine wake word ("Porcupine") wasn't ideal for the TV companion use case. Needed a custom wake word that matches the product name "R2T4".

**Changes Made:**
- `android/app/src/main/java/com/r2t4/app/audio/WakeWordDetector.kt` - Added custom wake word model loading from raw resources
- `android/app/src/main/res/raw/r_two_t_four.ppn` - Added Picovoice custom wake word model file
- `android/app/src/main/java/com/r2t4/app/ui/SettingsScreen.kt` - Updated UI text to reflect new wake word

**Why:** The built-in wake words (Porcupine, Alexa, Hey Google) don't match our product branding. Custom wake word provides a more natural and unique trigger phrase.

**How:**
1. Trained custom wake word model via Picovoice Console for phrase "R2T4"
2. Implemented resource extraction to copy .ppn file to internal storage at runtime
3. Modified Porcupine initialization to use custom keyword path instead of built-in keyword

**Technical Details:**
```kotlin
// Extract wake word file from resources
val inputStream = context.resources.openRawResource(R.raw.r_two_t_four)
val file = File(context.filesDir, "r_two_t_four.ppn")
inputStream.use { input ->
    FileOutputStream(file).use { output ->
        input.copyTo(output)
    }
}

// Initialize Porcupine with custom model
porcupine = Porcupine.Builder()
    .setAccessKey(accessKey)
    .setKeywordPath(file.absolutePath)
    .build(context)
```

**Follow-up Needed:**
- [ ] Validate detection accuracy in noisy environments
- [ ] Consider multiple wake word options in settings
- [ ] Add wake word sensitivity tuning

**Notes:** The custom wake word has similar detection accuracy to built-in keywords. Detection latency remains ~50ms. File extraction happens once per app install.

---

### 2026-01-02 - Camera Aspect Ratio Fix

**Context:** Images captured from the back camera were stretched or distorted, making TV content difficult to process.

**Changes Made:**
- `android/app/src/main/java/com/r2t4/app/camera/ImageCapturer.kt` - Set explicit 16:9 aspect ratio for ImageCapture use case

**Why:** CameraX was using default aspect ratio which didn't match typical TV screen proportions (16:9). This caused captured images to be stretched when the camera sensor had a different native ratio.

**How:** Set explicit aspect ratio constraint in ImageCapture.Builder:
```kotlin
val aspectRatio = AspectRatio.RATIO_16_9
imageCapture = ImageCapture.Builder()
    .setTargetAspectRatio(aspectRatio)
    .setJpegQuality(jpegQuality)
    .build()
```

**Follow-up Needed:**
- [ ] Test on devices with different camera sensors
- [ ] Consider making aspect ratio configurable in settings

**Notes:** Tested on Moto Z Play (2016). Images now properly capture TV content without distortion. May need adjustment for ultrawide or different aspect ratio TVs in the future.

---

### 2026-01-02 - Microphone Source Selection

**Context:** Wake word detection accuracy varied significantly based on device and environment. Default microphone source applies audio processing that can interfere with wake word detection.

**Changes Made:**
- `android/app/src/main/java/com/r2t4/app/audio/AudioRecorder.kt` - Added configurable MediaRecorder.AudioSource parameter
- `android/app/src/main/java/com/r2t4/app/settings/SettingsRepository.kt` - Added micSource setting with DEFAULT/UNPROCESSED/VOICE_COMMUNICATION options
- `android/app/src/main/java/com/r2t4/app/ui/SettingsScreen.kt` - Added dropdown selector for microphone source
- `android/app/src/main/java/com/r2t4/app/service/CaptureService.kt` - Pass mic source to AudioRecorder on startup

**Why:**
- DEFAULT source applies echo cancellation, noise suppression, and AGC which can interfere with Porcupine
- UNPROCESSED provides raw mic input ideal for wake word detection
- VOICE_COMMUNICATION provides noise cancellation useful in very noisy environments

**How:** Extended audio recording configuration:
```kotlin
// In AudioRecorder
fun start(scope: CoroutineScope, micSource: Int = MediaRecorder.AudioSource.DEFAULT)

// In SettingsRepository
data class Settings(
    // ...
    val micSource: Int = MediaRecorder.AudioSource.DEFAULT
)
```

**Testing Results:**
- UNPROCESSED: Best wake word detection in most cases
- VOICE_COMMUNICATION: Better in noisy environments but slightly higher false negatives
- DEFAULT: Works but not optimal for wake word detection

**Follow-up Needed:**
- [ ] Add auto-detection/recommendation based on environment noise level
- [ ] Document which source works best for different device models

**Notes:** Users may need to experiment with different sources depending on their device and room acoustics. UNPROCESSED is recommended default going forward.

---

### 2026-01-02 - Prompt Recording Fixes

**Context:** Prompt audio was uploading but arriving as silent/empty files on the server. Multiple issues in the prompt recording and upload pipeline.

**Changes Made:**
- `android/app/src/main/java/com/r2t4/app/grpc/R2T4Client.kt` - Rewrote uploadFullPrompt() to properly generate WAV headers
- `android/app/src/main/java/com/r2t4/app/service/CaptureService.kt` - Added delay before fetching prompt response to allow server processing
- `android/app/src/main/java/com/r2t4/app/service/UploadManager.kt` - Increased retry attempts for prompts (priority queue)

**Why:**
1. Raw PCM audio data was being sent without WAV container format
2. Client was requesting response before server finished processing upload
3. Prompts are high-priority and need more aggressive retry logic

**How:**

WAV Header Generation:
```kotlin
private fun createWavHeader(
    dataSize: Int,
    sampleRate: Int = 16000,
    channels: Int = 1,
    bitsPerSample: Int = 16
): ByteArray {
    val header = ByteBuffer.allocate(44).order(ByteOrder.LITTLE_ENDIAN)
    // RIFF chunk
    header.put("RIFF".toByteArray())
    header.putInt(36 + dataSize)
    header.put("WAVE".toByteArray())
    // fmt chunk
    header.put("fmt ".toByteArray())
    header.putInt(16) // fmt chunk size
    header.putShort(1) // audio format (PCM)
    header.putShort(channels.toShort())
    header.putInt(sampleRate)
    header.putInt(sampleRate * channels * bitsPerSample / 8) // byte rate
    header.putShort((channels * bitsPerSample / 8).toShort()) // block align
    header.putShort(bitsPerSample.toShort())
    // data chunk
    header.put("data".toByteArray())
    header.putInt(dataSize)
    return header.array()
}
```

Priority Upload Logic:
```kotlin
// Prompts get more retries and shorter delays
while (retries < MAX_RETRIES * 2 && !success) {
    when (val result = client.uploadFullPrompt(deviceId, promptResult)) {
        is R2T4Client.UploadResult.Success -> success = true
        is R2T4Client.UploadResult.Error -> {
            retries++
            delay(500L) // Shorter delay than ambient data
        }
    }
}
```

**Follow-up Needed:**
- [ ] Consider streaming prompt upload instead of single request
- [ ] Add progress indicator for prompt processing
- [ ] Implement prompt cancellation on server side

**Notes:** WAV format is essential for server-side processing. Browser-based admin UI can now play prompt audio directly. Response fetch delay of 1000ms works but could be replaced with polling or server push.

---

### 2026-01-02 - Silent Audio Recording Fix

**Context:** Even after initial audio recording implementation, some edge cases produced silent audio chunks (all zeros).

**Changes Made:**
- `android/app/src/main/java/com/r2t4/app/audio/AudioRecorder.kt` - Improved AudioRecord initialization and state validation
- Added buffer validation before emitting audio chunks
- Enhanced error logging for silent audio detection

**Why:** AudioRecord can be in RECORDING state but not producing data in certain edge cases (device busy, permission revoked, hardware issue).

**How:** Added validation:
```kotlin
// Check for silent audio before emitting
val audioData = buffer.array()
val hasAudio = audioData.any { it != 0.toShort() }
if (!hasAudio) {
    Log.w(TAG, "Silent audio detected, skipping chunk")
    continue
}
```

**Follow-up Needed:**
- [ ] Add audio level monitoring to UI
- [ ] Alert user if prolonged silence detected
- [ ] Investigate device-specific issues on Android 8

**Notes:** Issue was most common on cold start. Waiting for AudioRecord to fully initialize before reading resolves most cases.

---

### 2026-01-01 - Initial MVP1 Implementation

**Context:** Starting R2T4 project from scratch. Need to validate the capture-upload pipeline before investing in AI processing infrastructure.

**Changes Made:**
- Created full project structure (proto, server, android, docs)
- Implemented Go server with Connect-RPC
- Implemented Android client with all capture components
- Set up build scripts and documentation

**Why:** MVP1 focuses on proving the reliability of continuous capture and upload on older Android devices. Processing can come later once we validate the pipeline.

**How:**

**Server (Go)**:
- Connect-RPC handlers for Upload, Prompt, and Admin services
- File-based storage organized by device ID and timestamp
- Embedded web UI for browsing captured data
- Health and stats endpoints

**Client (Kotlin)**:
- CaptureService: Foreground service orchestrating all operations
- AudioRecorder: 16kHz PCM continuous recording with dual outputs
- WakeWordDetector: Porcupine integration (initially with built-in keyword)
- PromptRecorder: VAD-based prompt capture
- ImageCapturer: CameraX-based periodic photo capture
- UploadManager: Queue-based upload with exponential backoff retry
- SettingsScreen: SQLite-backed configuration

**Protocol**:
- Protobuf service definitions for Upload, Prompt, Admin
- Buf CLI for code generation to Go and Kotlin

**Architecture Decisions:**
1. File-based storage (not database) - Simpler, direct browser access
2. Connect-RPC - gRPC-compatible but browser-friendly
3. Foreground service - Required for reliable long-running capture
4. Dual audio outputs - Chunks for upload, frames for wake word
5. SQLite settings - Persist across updates
6. No authentication in MVP1 - LAN-only deployment

**Testing:**
- Tested on Moto Z Play (2016, Android 8, Snapdragon 625)
- Validated 8+ hour continuous operation
- Verified <1% chunk loss over local WiFi
- Confirmed wake word latency <100ms

**Follow-up Needed:**
- [ ] Add comprehensive unit tests
- [ ] Profile memory usage over 24h runs
- [ ] Test on variety of Android devices
- [ ] Measure battery impact (although device stays plugged in)

**Notes:**
- Total implementation time: ~2 days for MVP1
- Used Claude Code for assistance with both Go and Kotlin (learning both)
- Prioritized working end-to-end pipeline over features
- All major issues resolved in subsequent commits

**Known Issues Resolved:**
- ✅ Silent audio (buffer initialization)
- ✅ Empty prompts (WAV encoding)
- ✅ Stretched images (aspect ratio)
- ✅ Wake word false negatives (mic source)

---

## Development Metrics

### MVP1 Stats
- **Lines of Code**: ~5,300 total
  - Go server: ~2,000
  - Kotlin client: ~3,000
  - Proto definitions: ~300
- **Time to MVP1**: 2 days
- **Commits**: 9
- **Test Device**: Moto Z Play 2016 (Android 8, 3GB RAM, Snapdragon 625)
- **Reliability Target**: 8 hours @ <1% chunk loss ✅

### Tech Stack Evaluation
- **Go + Connect-RPC**: ⭐⭐⭐⭐⭐ Excellent. Fast development, browser-friendly.
- **Kotlin + Coroutines**: ⭐⭐⭐⭐⭐ Perfect for async operations. Clean code.
- **CameraX**: ⭐⭐⭐⭐ Good. Some aspect ratio quirks but overall solid.
- **Porcupine**: ⭐⭐⭐⭐ Very good. Accurate, low latency, but requires access key.
- **Protobuf + Buf**: ⭐⭐⭐⭐⭐ Flawless. Code generation just works.

---

## Next Phase: MVP2

### Planned Features
1. **Context Processing (Server)**
   - Continuous speech-to-text (Whisper or cloud STT)
   - Image scene understanding (CLIP or similar)
   - Sliding context window (last 5 minutes)
   - Temporal correlation of audio + images

2. **Intelligent Responses (Server)**
   - LLM integration (local or API)
   - RAG over captured context
   - Multi-modal understanding
   - Conversation history

3. **Advanced Wake Word**
   - Server-side wake word detection option
   - Voice identification (household members)
   - Custom end-word detection
   - Better noise handling

4. **Infrastructure**
   - Remote server support with TLS
   - Multi-device coordination
   - Session management
   - Data retention policies
   - Authentication/authorization

### Technical Challenges Ahead
- **Compute requirements**: STT + image processing is resource-intensive
- **Latency goals**: Need near-real-time responses
- **Privacy boundaries**: Process locally vs cloud trade-offs
- **Cost considerations**: Cloud API costs at scale
- **Storage growth**: Continuous capture generates significant data

### Open Questions
- Which STT engine? (Whisper, cloud APIs, other)
- Which LLM? (local models, OpenAI, Anthropic, other)
- How much context to retain? (storage/processing trade-off)
- Should we support optional cloud processing? (user choice)

---

## Lessons Learned

### What Worked Well
1. **Proto-first design** - Defining API contract upfront enabled parallel development
2. **Real hardware testing** - Caught issues emulator would miss
3. **Incremental commits** - Easy to bisect when issues arose
4. **File-based storage** - Simpler than database, works great for MVP
5. **Connect-RPC** - Browser compatibility without proxy is huge win

### What Was Challenging
1. **Audio buffer management** - Timing between chunks and frames required care
2. **Porcupine integration** - Sparse documentation, needed experimentation
3. **WAV encoding** - Had to implement from scratch
4. **CameraX quirks** - Aspect ratio behavior not intuitive
5. **Learning two languages** - Go and Kotlin simultaneously was ambitious but rewarding

### What Would We Do Differently
1. **Add tests earlier** - Would have caught silent audio issue faster
2. **More detailed logging** - Some issues took longer to debug than needed
3. **Prototype on emulator first** - Some device deployment delays could have been avoided
4. **Version control for .ppn files** - Binary files in git not ideal

### Advice for Future Contributors
1. Test on real hardware from the start
2. Read AGENTS.md and questions_answers.md before coding
3. Update this DEVLOG.md with significant changes
4. Keep commits focused and atomic
5. Don't skimp on error handling and logging

---

## References
- **Architecture**: `AGENTS.md`
- **Setup**: `docs/setup.md`
- **Building**: `docs/building.md`
- **Design Decisions**: `questions_answers.md`
- **README**: `readme.md`
