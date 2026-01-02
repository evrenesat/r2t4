package com.r2t4.app.service

import android.util.Log
import com.r2t4.app.audio.AudioRecorder
import com.r2t4.app.audio.PromptRecorder
import com.r2t4.app.camera.ImageCapturer
import com.r2t4.app.grpc.R2T4Client
import kotlinx.coroutines.*
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.flow.*

/**
 * UploadManager handles queuing and uploading of audio chunks, images, and prompts.
 * Implements retry logic with exponential backoff and backlog management.
 */
class UploadManager(
    private val client: R2T4Client,
    private val deviceId: String
) {
    companion object {
        private const val TAG = "UploadManager"
        private const val MAX_BACKLOG_SECONDS = 120  // 2 minutes
        private const val MAX_RETRIES = 3
        private const val BASE_RETRY_DELAY_MS = 1000L
    }

    // Upload queues
    private val audioQueue = Channel<AudioRecorder.AudioChunk>(Channel.BUFFERED)
    private val imageQueue = Channel<ImageCapturer.ImageFrame>(Channel.BUFFERED)
    private val promptQueue = Channel<PromptRecorder.PromptResult>(Channel.BUFFERED)

    // State
    private var uploadJob: Job? = null
    private var isRunning = false

    // Statistics
    private var audioChunksSent = 0
    private var audioChunksAcked = 0
    private var imagesSent = 0
    private var imagesAcked = 0
    private var promptsSent = 0

    // Backlog tracking
    private var oldestPendingTimestamp = 0L
    private var pendingCount = 0

    // Status flow
    private val _status = MutableStateFlow(UploadStatus())
    val status: StateFlow<UploadStatus> = _status.asStateFlow()

    data class UploadStatus(
        val isConnected: Boolean = false,
        val pendingAudioChunks: Int = 0,
        val pendingImages: Int = 0,
        val audioChunksSent: Int = 0,
        val imagesSent: Int = 0,
        val lastError: String? = null,
        val backlogExceeded: Boolean = false
    )

    /**
     * Start the upload manager.
     */
    fun start(scope: CoroutineScope) {
        if (isRunning) return

        isRunning = true
        Log.i(TAG, "Upload manager started for device: $deviceId")

        uploadJob = scope.launch {
            // Launch parallel upload workers
            launch { processAudioQueue() }
            launch { processImageQueue() }
            launch { processPromptQueue() }
        }
    }

    /**
     * Stop the upload manager.
     */
    fun stop() {
        isRunning = false
        uploadJob?.cancel()
        uploadJob = null
        Log.i(TAG, "Upload manager stopped")
    }

    /**
     * Queue an audio chunk for upload.
     */
    suspend fun queueAudioChunk(chunk: AudioRecorder.AudioChunk) {
        if (!isRunning) return

        // Check backlog
        if (checkBacklog(chunk.startTimestampMs)) {
            audioQueue.send(chunk)
            pendingCount++
            updateStatus()
        }
    }

    /**
     * Queue an image frame for upload.
     */
    suspend fun queueImageFrame(frame: ImageCapturer.ImageFrame) {
        if (!isRunning) return

        if (checkBacklog(frame.timestampMs)) {
            imageQueue.send(frame)
            pendingCount++
            updateStatus()
        }
    }

    /**
     * Queue a full prompt for upload (priority).
     */
    suspend fun queuePrompt(result: PromptRecorder.PromptResult) {
        if (!isRunning) return

        // Prompts are priority - always queue
        promptQueue.send(result)
        promptsSent++
    }

    /**
     * Check if backlog is within limits.
     */
    private fun checkBacklog(timestampMs: Long): Boolean {
        if (oldestPendingTimestamp == 0L) {
            oldestPendingTimestamp = timestampMs
        }

        val backlogMs = System.currentTimeMillis() - oldestPendingTimestamp
        val backlogSeconds = backlogMs / 1000

        if (backlogSeconds > MAX_BACKLOG_SECONDS) {
            Log.w(TAG, "Backlog exceeded: ${backlogSeconds}s > ${MAX_BACKLOG_SECONDS}s")
            _status.value = _status.value.copy(backlogExceeded = true)
            return false
        }

        return true
    }

    /**
     * Process audio upload queue.
     */
    private suspend fun processAudioQueue() {
        for (chunk in audioQueue) {
            if (!isRunning) break

            var retries = 0
            var success = false

            while (retries < MAX_RETRIES && !success) {
                when (val result = client.uploadAudioChunk(deviceId, chunk)) {
                    is R2T4Client.UploadResult.Success -> {
                        success = true
                        audioChunksAcked++
                        pendingCount--
                        updateOldestPending()
                        updateStatus()
                    }
                    is R2T4Client.UploadResult.Error -> {
                        retries++
                        if (retries < MAX_RETRIES) {
                            val delay = BASE_RETRY_DELAY_MS * (1 shl retries)
                            Log.w(TAG, "Audio upload failed, retry $retries in ${delay}ms: ${result.message}")
                            delay(delay)
                        } else {
                            Log.e(TAG, "Audio upload failed after $MAX_RETRIES retries: ${result.message}")
                            _status.value = _status.value.copy(lastError = result.message)
                        }
                    }
                }
            }

            audioChunksSent++
        }
    }

    /**
     * Process image upload queue.
     */
    private suspend fun processImageQueue() {
        for (frame in imageQueue) {
            if (!isRunning) break

            var retries = 0
            var success = false

            while (retries < MAX_RETRIES && !success) {
                when (val result = client.uploadImageFrame(deviceId, frame)) {
                    is R2T4Client.UploadResult.Success -> {
                        success = true
                        imagesAcked++
                        pendingCount--
                        updateOldestPending()
                        updateStatus()
                    }
                    is R2T4Client.UploadResult.Error -> {
                        retries++
                        if (retries < MAX_RETRIES) {
                            val delay = BASE_RETRY_DELAY_MS * (1 shl retries)
                            Log.w(TAG, "Image upload failed, retry $retries in ${delay}ms: ${result.message}")
                            delay(delay)
                        } else {
                            Log.e(TAG, "Image upload failed after $MAX_RETRIES retries: ${result.message}")
                            _status.value = _status.value.copy(lastError = result.message)
                        }
                    }
                }
            }

            imagesSent++
        }
    }

    /**
     * Process prompt upload queue (priority).
     */
    private suspend fun processPromptQueue() {
        for (promptResult in promptQueue) {
            if (!isRunning) break

            Log.d(TAG, "Uploading full prompt: ${promptResult.promptId}")

            // Prompts get more retries and shorter delays
            var retries = 0
            var success = false

            while (retries < MAX_RETRIES * 2 && !success) {
                when (val result = client.uploadFullPrompt(deviceId, promptResult)) {
                    is R2T4Client.UploadResult.Success -> {
                        success = true
                        Log.d(TAG, "Prompt uploaded: ${promptResult.promptId}")
                    }
                    is R2T4Client.UploadResult.Error -> {
                        retries++
                        if (retries < MAX_RETRIES * 2) {
                            delay(500L)
                        } else {
                            Log.e(TAG, "Prompt upload failed finally: ${result.message}")
                        }
                    }
                }
            }
        }
    }

    private fun updateOldestPending() {
        if (pendingCount == 0) {
            oldestPendingTimestamp = 0L
        }
    }

    private fun updateStatus() {
        _status.value = UploadStatus(
            isConnected = true,
            pendingAudioChunks = pendingCount,
            pendingImages = 0, // Could track separately
            audioChunksSent = audioChunksSent,
            imagesSent = imagesSent,
            lastError = _status.value.lastError,
            backlogExceeded = _status.value.backlogExceeded
        )
    }

    /**
     * Get upload statistics.
     */
    fun getStats(): Map<String, Int> = mapOf(
        "audioChunksSent" to audioChunksSent,
        "audioChunksAcked" to audioChunksAcked,
        "imagesSent" to imagesSent,
        "imagesAcked" to imagesAcked,
        "promptsSent" to promptsSent,
        "pendingCount" to pendingCount
    )
}
