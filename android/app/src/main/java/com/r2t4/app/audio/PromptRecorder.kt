package com.r2t4.app.audio

import android.util.Log
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.SharedFlow
import java.io.ByteArrayOutputStream
import java.util.UUID

/**
 * PromptRecorder captures audio after wake word detection until:
 * 1. VAD detects silence (energy-based)
 * 2. Timeout is reached
 * 3. User presses Done/Cancel button
 */
class PromptRecorder {

    companion object {
        private const val TAG = "PromptRecorder"
        
        // Simple energy-based VAD parameters
        private const val SILENCE_THRESHOLD = 500       // Energy threshold for silence
        private const val SILENCE_DURATION_MS = 1500    // 1.5 seconds of silence to stop
        private const val MIN_SPEECH_MS = 500           // Minimum speech before checking for silence
    }

    // Recording state
    private var isRecording = false
    private var promptId: String = ""
    private var startTimeMs: Long = 0
    private var timeoutSeconds: Int = 15

    // Audio buffer
    private val audioBuffer = ByteArrayOutputStream()
    private var sampleCount = 0

    // Silence detection
    private var lastSpeechTimeMs: Long = 0
    private var isSpeaking = false

    // Coroutine job for timeout
    private var timeoutJob: Job? = null

    // Result states
    enum class EndReason {
        USER_DONE,      // User pressed Done button
        USER_CANCEL,    // User pressed Cancel button
        SILENCE,        // VAD detected silence
        TIMEOUT         // Timeout reached
    }

    /**
     * Prompt recording result.
     */
    data class PromptResult(
        val promptId: String,
        val wavData: ByteArray,
        val startTimeMs: Long,
        val endTimeMs: Long,
        val endReason: EndReason
    ) {
        override fun equals(other: Any?): Boolean {
            if (this === other) return true
            if (javaClass != other?.javaClass) return false
            other as PromptResult
            return promptId == other.promptId
        }
        override fun hashCode(): Int = promptId.hashCode()
    }

    // Flow for completed prompts
    private val _promptCompleted = MutableSharedFlow<PromptResult>(replay = 0, extraBufferCapacity = 5)
    val promptCompleted: SharedFlow<PromptResult> = _promptCompleted

    // Flow for prompt audio chunks (for streaming upload)
    private val _promptChunk = MutableSharedFlow<PromptChunk>(replay = 0, extraBufferCapacity = 20)
    val promptChunks: SharedFlow<PromptChunk> = _promptChunk

    data class PromptChunk(
        val promptId: String,
        val chunkIndex: Int,
        val audioData: ByteArray,
        val isFinal: Boolean,
        val endReason: EndReason?,
        val timestampMs: Long
    )

    private var chunkIndex = 0
    private var pendingChunkData = ByteArrayOutputStream()
    private val chunkSize = 16000 * 2 // 1 second of audio (16kHz * 2 bytes per sample)

    /**
     * Start recording a prompt.
     */
    fun start(scope: CoroutineScope, timeoutSeconds: Int = 15) {
        if (isRecording) {
            Log.w(TAG, "Already recording a prompt")
            return
        }

        this.timeoutSeconds = timeoutSeconds
        // Use time-ordered ID (timestamp-uuid) for easier debugging/sorting
        promptId = "${System.currentTimeMillis()}-${UUID.randomUUID()}"
        startTimeMs = System.currentTimeMillis()
        lastSpeechTimeMs = startTimeMs
        isRecording = true
        isSpeaking = false
        audioBuffer.reset()
        pendingChunkData.reset()
        sampleCount = 0
        chunkIndex = 0

        Log.i(TAG, "Prompt recording started: $promptId (timeout: ${timeoutSeconds}s)")

        // Start timeout timer
        timeoutJob = scope.launch {
            delay(timeoutSeconds * 1000L)
            if (isRecording) {
                Log.i(TAG, "Prompt timeout reached")
                finishPrompt(EndReason.TIMEOUT)
            }
        }
    }

    /**
     * Process an audio frame during prompt recording.
     */
    fun processFrame(audioFrame: ShortArray) {
        if (!isRecording) return

        // Calculate energy (simple RMS)
        var sumSquares = 0L
        for (sample in audioFrame) {
            sumSquares += sample.toLong() * sample.toLong()
        }
        val energy = kotlin.math.sqrt(sumSquares.toDouble() / audioFrame.size).toInt()

        // Update speech detection
        val now = System.currentTimeMillis()
        val elapsedMs = now - startTimeMs

        if (energy > SILENCE_THRESHOLD) {
            lastSpeechTimeMs = now
            isSpeaking = true
        }

        // Check for silence (only after minimum speech time)
        if (isSpeaking && elapsedMs > MIN_SPEECH_MS) {
            val silenceDuration = now - lastSpeechTimeMs
            if (silenceDuration > SILENCE_DURATION_MS) {
                Log.i(TAG, "Silence detected after ${elapsedMs}ms")
                finishPrompt(EndReason.SILENCE)
                return
            }
        }

        // Add to buffer
        for (sample in audioFrame) {
            audioBuffer.write(sample.toInt() and 0xFF)
            audioBuffer.write((sample.toInt() shr 8) and 0xFF)
            pendingChunkData.write(sample.toInt() and 0xFF)
            pendingChunkData.write((sample.toInt() shr 8) and 0xFF)
        }
        sampleCount += audioFrame.size

        // Emit chunk for streaming upload
        if (pendingChunkData.size() >= chunkSize) {
            val chunkData = pendingChunkData.toByteArray()
            _promptChunk.tryEmit(PromptChunk(
                promptId = promptId,
                chunkIndex = chunkIndex++,
                audioData = chunkData,
                isFinal = false,
                endReason = null,
                timestampMs = now
            ))
            pendingChunkData.reset()
        }
    }

    /**
     * User pressed Done button.
     */
    fun userDone() {
        if (isRecording) {
            finishPrompt(EndReason.USER_DONE)
        }
    }

    /**
     * User pressed Cancel button.
     */
    fun userCancel() {
        if (isRecording) {
            finishPrompt(EndReason.USER_CANCEL)
        }
    }

    /**
     * Check if currently recording.
     */
    fun isRecording(): Boolean = isRecording

    /**
     * Get current prompt ID.
     */
    fun getCurrentPromptId(): String = promptId

    /**
     * Finish prompt recording and emit result.
     */
    private fun finishPrompt(reason: EndReason) {
        if (!isRecording) return

        isRecording = false
        timeoutJob?.cancel()
        timeoutJob = null

        val endTimeMs = System.currentTimeMillis()
        val pcmData = audioBuffer.toByteArray()

        // Emit final chunk
        val remainingData = pendingChunkData.toByteArray()
        if (remainingData.isNotEmpty() || reason != EndReason.USER_CANCEL) {
            _promptChunk.tryEmit(PromptChunk(
                promptId = promptId,
                chunkIndex = chunkIndex,
                audioData = remainingData,
                isFinal = true,
                endReason = reason,
                timestampMs = endTimeMs
            ))
        }

        // Create WAV file
        val wavData = createWavFile(pcmData, 16000, 1, 16)

        val result = PromptResult(
            promptId = promptId,
            wavData = wavData,
            startTimeMs = startTimeMs,
            endTimeMs = endTimeMs,
            endReason = reason
        )

        _promptCompleted.tryEmit(result)

        Log.i(TAG, "Prompt completed: $promptId, reason=$reason, duration=${endTimeMs - startTimeMs}ms, size=${wavData.size}")
    }

    /**
     * Create a WAV file from raw PCM data.
     */
    private fun createWavFile(pcmData: ByteArray, sampleRate: Int, channels: Int, bitsPerSample: Int): ByteArray {
        val byteRate = sampleRate * channels * bitsPerSample / 8
        val blockAlign = channels * bitsPerSample / 8
        val dataSize = pcmData.size
        val fileSize = 36 + dataSize

        val header = ByteArray(44)
        
        // RIFF header
        header[0] = 'R'.code.toByte()
        header[1] = 'I'.code.toByte()
        header[2] = 'F'.code.toByte()
        header[3] = 'F'.code.toByte()
        writeInt(header, 4, fileSize)
        header[8] = 'W'.code.toByte()
        header[9] = 'A'.code.toByte()
        header[10] = 'V'.code.toByte()
        header[11] = 'E'.code.toByte()

        // fmt chunk
        header[12] = 'f'.code.toByte()
        header[13] = 'm'.code.toByte()
        header[14] = 't'.code.toByte()
        header[15] = ' '.code.toByte()
        writeInt(header, 16, 16)
        writeShort(header, 20, 1)
        writeShort(header, 22, channels)
        writeInt(header, 24, sampleRate)
        writeInt(header, 28, byteRate)
        writeShort(header, 32, blockAlign)
        writeShort(header, 34, bitsPerSample)

        // data chunk
        header[36] = 'd'.code.toByte()
        header[37] = 'a'.code.toByte()
        header[38] = 't'.code.toByte()
        header[39] = 'a'.code.toByte()
        writeInt(header, 40, dataSize)

        return header + pcmData
    }

    private fun writeInt(array: ByteArray, offset: Int, value: Int) {
        array[offset] = (value and 0xFF).toByte()
        array[offset + 1] = ((value shr 8) and 0xFF).toByte()
        array[offset + 2] = ((value shr 16) and 0xFF).toByte()
        array[offset + 3] = ((value shr 24) and 0xFF).toByte()
    }

    private fun writeShort(array: ByteArray, offset: Int, value: Int) {
        array[offset] = (value and 0xFF).toByte()
        array[offset + 1] = ((value shr 8) and 0xFF).toByte()
    }
}
