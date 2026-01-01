package com.r2t4.app.audio

import android.content.Context
import android.util.Log
import ai.picovoice.porcupine.Porcupine
import ai.picovoice.porcupine.PorcupineException
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.SharedFlow

/**
 * WakeWordDetector uses Porcupine to detect the wake word "Hey TV Mate".
 * Falls back to push-to-talk mode if initialization fails.
 */
class WakeWordDetector(private val context: Context) {

    companion object {
        private const val TAG = "WakeWordDetector"
        
        // Built-in wake word (Porcupine supports "Porcupine", "Alexa", "Hey Google", etc.)
        // For custom wake words, you need to train a model on Picovoice Console.
        // MVP1 uses "Porcupine" as the wake word for testing.
        private val BUILT_IN_KEYWORD = Porcupine.BuiltInKeyword.PORCUPINE
    }

    private var porcupine: Porcupine? = null
    private var isInitialized = false
    private var accessKey: String = ""

    // Flow for wake word detection events
    private val _wakeWordDetected = MutableSharedFlow<Long>(replay = 0, extraBufferCapacity = 5)
    val wakeWordDetected: SharedFlow<Long> = _wakeWordDetected

    /**
     * Initialize Porcupine with the given access key.
     * Returns true if successful, false if failed (push-to-talk fallback).
     */
    fun initialize(accessKey: String): Boolean {
        this.accessKey = accessKey
        
        if (accessKey.isBlank()) {
            Log.w(TAG, "No Porcupine access key provided, wake word disabled")
            return false
        }

        try {
            porcupine = Porcupine.Builder()
                .setAccessKey(accessKey)
                .setKeyword(BUILT_IN_KEYWORD)
                .build(context)

            isInitialized = true
            Log.i(TAG, "Porcupine initialized successfully with keyword: ${BUILT_IN_KEYWORD.name}")
            return true

        } catch (e: PorcupineException) {
            Log.e(TAG, "Failed to initialize Porcupine: ${e.message}")
            isInitialized = false
            return false
        } catch (e: Exception) {
            Log.e(TAG, "Unexpected error initializing Porcupine: ${e.message}")
            isInitialized = false
            return false
        }
    }

    /**
     * Process an audio frame (512 samples at 16kHz).
     * Returns the keyword index if detected, -1 otherwise.
     */
    fun processFrame(audioFrame: ShortArray): Int {
        if (!isInitialized || porcupine == null) {
            return -1
        }

        // Porcupine expects exactly 512 samples (frameLength)
        if (audioFrame.size != porcupine!!.frameLength) {
            // Pad or trim to match expected size
            val adjustedFrame = ShortArray(porcupine!!.frameLength)
            audioFrame.copyInto(adjustedFrame, 0, 0, minOf(audioFrame.size, adjustedFrame.size))
            return processFrameInternal(adjustedFrame)
        }

        return processFrameInternal(audioFrame)
    }

    private fun processFrameInternal(frame: ShortArray): Int {
        return try {
            val keywordIndex = porcupine!!.process(frame)
            if (keywordIndex >= 0) {
                Log.i(TAG, "Wake word detected! Keyword index: $keywordIndex")
                _wakeWordDetected.tryEmit(System.currentTimeMillis())
            }
            keywordIndex
        } catch (e: PorcupineException) {
            Log.e(TAG, "Error processing audio frame: ${e.message}")
            -1
        }
    }

    /**
     * Check if wake word detection is available.
     */
    fun isAvailable(): Boolean = isInitialized && porcupine != null

    /**
     * Get the expected frame length for audio processing.
     */
    fun getFrameLength(): Int = porcupine?.frameLength ?: 512

    /**
     * Get the expected sample rate.
     */
    fun getSampleRate(): Int = porcupine?.sampleRate ?: 16000

    /**
     * Release Porcupine resources.
     */
    fun release() {
        try {
            porcupine?.delete()
        } catch (e: Exception) {
            Log.e(TAG, "Error releasing Porcupine: ${e.message}")
        }
        porcupine = null
        isInitialized = false
        Log.d(TAG, "Porcupine released")
    }
}
