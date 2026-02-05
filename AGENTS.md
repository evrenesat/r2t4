# R2T4 Agent Guidelines

## Key Components (Agents)

The system is comprised of several distinct agents (components) with specific responsibilities. Detailed component descriptions are available in the full documentation, but the core agents are listed below:

1. **CaptureService** (orchestrator)
   - Coordinates all capture operations.
   - Manages the lifecycle of other agents.
   - Ensures background operation via Foreground Service.

2. **AudioRecorder**
   - Handles continuous 16kHz audio capture.
   - Provides dual outputs:
     - Chunks: For server archival (WAV).
     - Frames: For real-time processing (Wake Word/VAD).

3. **WakeWordDetector**
   - On-device detection using Picovoice Porcupine.
   - Listens for the custom "R2T4" wake word.
   - Triggers the transition to Prompt Recording mode.

4. **PromptRecorder**
   - Captures user queries once the wake word is triggered.
   - Uses Voice Activity Detection (VAD) to determine endpoint (silence).
   - Formats audio for the PromptService.

5. **ImageCapturer**
   - Handles periodic photo capture using CameraX.
   - Resizes and compresses images before handing them to the UploadManager.

6. **UploadManager**
   - Manages the upload queue.
   - Implements retry logic and backlog protection to prevent data loss or memory overflows.

7. **R2T4Client**
   - Connect-RPC client wrapper.
   - Handles network communication with the Go server.

## Agent Best Practices

When working with the R2T4 agent architecture, adhere to the following guidelines:

1. **Respect the Agent Architecture**
   - Each component has a single responsibility. Do not cross-contaminate logic (e.g., AudioRecorder should not know about UploadManager; it should just emit data).

2. **Use Coroutines Correctly**
   - Never block the main thread.
   - Use `suspend` functions for I/O and heavy processing.
   - Use `Flows` for continuous data streams between agents.

3. **Handle Failures Gracefully**
   - Agents should degrade functionality rather than crash the app.
   - If the Camera fails, Audio should continue.
   - If the Network fails, the UploadManager should queue locally up to the limit.

4. **Maintain Observability**
   - Agents should emit status updates via StateFlow/SharedFlow.
   - Logs should be structured and tagged with the agent name.

5. **Test on Real Hardware**
   - Emulator behavior differs significantly, especially for CameraX and AudioRecord timing.
   - Verify performance on target low-end devices.

6. **Consider Power/Performance**
   - This system runs for hours on old devices. Optimize for battery and thermal constraints.
   - Release resources (Camera, Mic) immediately when the service stops.

7. **Privacy First**
   - All data stays on the user's infrastructure.
   - No data is sent to third-party clouds unless explicitly configured by the user in future updates.

## Protocol & Interaction Logic

### Wake Word Flow
The interaction between agents during a wake word event is time-critical:
1. `AudioRecorder` pushes frames to `WakeWordDetector`.
2. `WakeWordDetector` identifies "R2T4".
3. `CaptureService` pauses `AudioRecorder` archival stream (optional) and starts `PromptRecorder`.
4. `PromptRecorder` captures specific audio until VAD silence.
5. `UploadManager` prioritizes the Prompt upload over background chunks.

### Backlog Management
The `UploadManager` enforces a strict backlog limit (currently 2 minutes of buffer). If the server is unreachable:
1. Retries continue with exponential backoff.
2. If the buffer exceeds the limit, the oldest chunks are dropped to preserve memory stability.
