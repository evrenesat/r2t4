package com.r2t4.app.service

import android.app.Notification
import android.app.PendingIntent
import android.app.Service
import android.content.Intent
import android.os.IBinder
import android.util.Log
import androidx.core.app.NotificationCompat
import androidx.lifecycle.LifecycleService
import androidx.lifecycle.lifecycleScope
import com.r2t4.app.MainActivity
import com.r2t4.app.R
import com.r2t4.app.R2T4Application
import com.r2t4.app.audio.AudioRecorder
import com.r2t4.app.audio.PromptRecorder
import com.r2t4.app.audio.WakeWordDetector
import com.r2t4.app.camera.ImageCapturer
import com.r2t4.app.grpc.R2T4Client
import com.r2t4.app.settings.SettingsRepository
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.*

/**
 * CaptureService is a foreground service that orchestrates all capture operations.
 * Manages AudioRecorder, ImageCapturer, WakeWordDetector, and UploadManager.
 */
class CaptureService : LifecycleService() {

    companion object {
        private const val TAG = "CaptureService"
        private const val NOTIFICATION_ID = 1

        // Service actions
        const val ACTION_START = "com.r2t4.app.action.START"
        const val ACTION_STOP = "com.r2t4.app.action.STOP"
        const val ACTION_PUSH_TO_TALK = "com.r2t4.app.action.PUSH_TO_TALK"
        const val ACTION_PROMPT_DONE = "com.r2t4.app.action.PROMPT_DONE"
        const val ACTION_PROMPT_CANCEL = "com.r2t4.app.action.PROMPT_CANCEL"

        // Singleton state access
        private var instance: CaptureService? = null
        val stateFlow: StateFlow<CaptureState> get() = _stateFlow.asStateFlow()
        private val _stateFlow = MutableStateFlow(CaptureState())
    }

    // Components
    private lateinit var settingsRepository: SettingsRepository
    private lateinit var audioRecorder: AudioRecorder
    private lateinit var wakeWordDetector: WakeWordDetector
    private lateinit var promptRecorder: PromptRecorder
    private lateinit var imageCapturer: ImageCapturer
    private lateinit var grpcClient: R2T4Client
    private var uploadManager: UploadManager? = null

    // Current settings
    private var currentSettings = SettingsRepository.Settings()

    // Capture state
    data class CaptureState(
        val isRunning: Boolean = false,
        val isListening: Boolean = false,
        val isPrompting: Boolean = false,
        val wakeWordEnabled: Boolean = false,
        val cameraEnabled: Boolean = false,
        val lastError: String? = null,
        val logMessages: List<LogEntry> = emptyList(),
        val uploadStats: Map<String, Int> = emptyMap()
    )

    data class LogEntry(
        val timestamp: Long,
        val message: String,
        val type: LogType
    )

    enum class LogType {
        INFO, WARNING, ERROR, RESPONSE
    }

    override fun onCreate() {
        super.onCreate()
        instance = this

        // Initialize components
        settingsRepository = SettingsRepository(this)
        audioRecorder = AudioRecorder(this)
        wakeWordDetector = WakeWordDetector(this)
        promptRecorder = PromptRecorder()
        imageCapturer = ImageCapturer(this)
        grpcClient = R2T4Client()

        Log.i(TAG, "CaptureService created")
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        super.onStartCommand(intent, flags, startId)

        when (intent?.action) {
            ACTION_START -> startCapture()
            ACTION_STOP -> stopCapture()
            ACTION_PUSH_TO_TALK -> startPromptCapture()
            ACTION_PROMPT_DONE -> promptRecorder.userDone()
            ACTION_PROMPT_CANCEL -> promptRecorder.userCancel()
        }

        return Service.START_STICKY
    }

    override fun onBind(intent: Intent): IBinder? {
        super.onBind(intent)
        return null
    }

    override fun onDestroy() {
        stopCapture()
        instance = null
        super.onDestroy()
        Log.i(TAG, "CaptureService destroyed")
    }

    /**
     * Start the capture service.
     */
    private fun startCapture() {
        if (_stateFlow.value.isRunning) {
            Log.w(TAG, "Capture already running")
            return
        }

        startForeground(NOTIFICATION_ID, createNotification())

        lifecycleScope.launch {
            // Load settings
            settingsRepository.settingsFlow.first().let { settings ->
                currentSettings = settings

                // Initialize gRPC client
                grpcClient.initialize(settings.serverAddress)

                // Initialize upload manager
                uploadManager = UploadManager(grpcClient, settings.deviceId)
                uploadManager?.start(lifecycleScope)

                // Configure audio recorder
                audioRecorder.chunkDurationSeconds = settings.audioChunkDuration

                // Initialize wake word detector
                val wakeWordEnabled = if (!settings.pushToTalkMode && settings.porcupineAccessKey.isNotBlank()) {
                    wakeWordDetector.initialize(settings.porcupineAccessKey)
                } else {
                    false
                }

                // Initialize camera
                val cameraEnabled = imageCapturer.hasPermission() && imageCapturer.hasCameraHardware()
                if (cameraEnabled) {
                    imageCapturer.captureIntervalSeconds = settings.photoInterval
                    imageCapturer.jpegQuality = settings.photoQuality
                    // Camera initialization requires lifecycle owner - done in MainActivity
                }

                updateState {
                    it.copy(
                        isRunning = true,
                        isListening = true,
                        wakeWordEnabled = wakeWordEnabled,
                        cameraEnabled = cameraEnabled
                    )
                }

                addLog("R2T4 capture started", LogType.INFO)
                if (!wakeWordEnabled) {
                    addLog("Wake word disabled - use push-to-talk", LogType.WARNING)
                }
            }

            // Start audio recording
            if (audioRecorder.hasPermission()) {
                audioRecorder.start(lifecycleScope)
                
                // Collect audio chunks for upload
                launch {
                    audioRecorder.audioChunks.collect { chunk ->
                        if (!promptRecorder.isRecording()) {
                            uploadManager?.queueAudioChunk(chunk)
                        }
                    }
                }

                // Process audio frames for wake word detection
                launch {
                    audioRecorder.audioFrames.collect { frame ->
                        if (_stateFlow.value.wakeWordEnabled && !promptRecorder.isRecording()) {
                            val result = wakeWordDetector.processFrame(frame)
                            if (result >= 0) {
                                startPromptCapture()
                            }
                        }
                        
                        // Also feed to prompt recorder if active
                        if (promptRecorder.isRecording()) {
                            promptRecorder.processFrame(frame)
                        }
                    }
                }
            }

            // Collect wake word detections
            launch {
                wakeWordDetector.wakeWordDetected.collect { timestamp ->
                    addLog("Wake word detected!", LogType.INFO)
                }
            }

            // Collect prompt completions
            launch {
                promptRecorder.promptCompleted.collect { result ->
                    updateState { it.copy(isPrompting = false) }
                    
                    when (result.endReason) {
                        PromptRecorder.EndReason.USER_CANCEL -> {
                            addLog("Prompt cancelled", LogType.INFO)
                        }
                        else -> {
                            addLog("Prompt recorded (${result.endTimeMs - result.startTimeMs}ms)", LogType.INFO)
                            
                            // Get response from server
                            launch {
                                delay(500) // Give server time to process
                                when (val response = grpcClient.getPromptResponse(
                                    currentSettings.deviceId,
                                    result.promptId
                                )) {
                                    is R2T4Client.PromptResponse.Completed -> {
                                        addLog(response.responseText, LogType.RESPONSE)
                                    }
                                    is R2T4Client.PromptResponse.Error -> {
                                        addLog("Error: ${response.message}", LogType.ERROR)
                                    }
                                    else -> {}
                                }
                            }
                        }
                    }
                }
            }

            // Collect prompt chunks for streaming upload
            launch {
                promptRecorder.promptChunks.collect { chunk ->
                    uploadManager?.queuePromptChunk(chunk)
                }
            }

            // Collect image frames for upload
            launch {
                imageCapturer.imageFrames.collect { frame ->
                    uploadManager?.queueImageFrame(frame)
                }
            }

            // Collect upload status
            launch {
                uploadManager?.status?.collect { status ->
                    updateState { it.copy(uploadStats = uploadManager?.getStats() ?: emptyMap()) }
                    
                    if (status.backlogExceeded) {
                        addLog("Upload backlog exceeded - check server connection", LogType.ERROR)
                        stopCapture()
                    }
                }
            }
        }
    }

    /**
     * Stop the capture service.
     */
    private fun stopCapture() {
        audioRecorder.stop()
        imageCapturer.stopCapture()
        wakeWordDetector.release()
        uploadManager?.stop()

        updateState { CaptureState() }
        addLog("R2T4 capture stopped", LogType.INFO)

        stopForeground(Service.STOP_FOREGROUND_REMOVE)
        stopSelf()
    }

    /**
     * Start prompt capture (after wake word or push-to-talk).
     */
    private fun startPromptCapture() {
        if (promptRecorder.isRecording()) return

        updateState { it.copy(isPrompting = true) }
        promptRecorder.start(lifecycleScope, currentSettings.promptTimeout)
        addLog("Listening for prompt...", LogType.INFO)
    }

    /**
     * Add a log message.
     */
    private fun addLog(message: String, type: LogType) {
        val entry = LogEntry(System.currentTimeMillis(), message, type)
        updateState { state ->
            val logs = (state.logMessages + entry).takeLast(100) // Keep last 100 messages
            state.copy(logMessages = logs)
        }
        Log.d(TAG, "[${type.name}] $message")
    }

    /**
     * Update state atomically.
     */
    private fun updateState(update: (CaptureState) -> CaptureState) {
        _stateFlow.value = update(_stateFlow.value)
    }

    /**
     * Create the foreground notification.
     */
    private fun createNotification(): Notification {
        val intent = Intent(this, MainActivity::class.java)
        val pendingIntent = PendingIntent.getActivity(
            this, 0, intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )

        return NotificationCompat.Builder(this, R2T4Application.NOTIFICATION_CHANNEL_ID)
            .setContentTitle("R2T4 Active")
            .setContentText("Capturing audio and video")
            .setSmallIcon(android.R.drawable.ic_btn_speak_now)
            .setContentIntent(pendingIntent)
            .setOngoing(true)
            .build()
    }
}
