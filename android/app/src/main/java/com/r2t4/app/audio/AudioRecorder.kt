package com.r2t4.app.audio

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import android.util.Log
import androidx.core.content.ContextCompat
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.SharedFlow
import java.io.ByteArrayOutputStream

/**
 * AudioRecorder handles continuous audio capture at 16kHz mono.
 * Emits audio chunks of configurable duration for upload.
 * Also provides raw audio frames for wake word detection.
 */
class AudioRecorder(private val context: Context) {

    companion object {
        private const val TAG = "AudioRecorder"
        const val SAMPLE_RATE = 16000
        const val CHANNEL_CONFIG = AudioFormat.CHANNEL_IN_MONO
        const val AUDIO_FORMAT = AudioFormat.ENCODING_PCM_16BIT
        
        // Frame size for wake word (512 samples = 32ms at 16kHz)
        const val FRAME_SIZE = 512
    }

    // Audio recording state
    private var audioRecord: AudioRecord? = null
    private var recordingJob: Job? = null
    private var isRecording = false

    // Chunk duration in seconds (configurable)
    var chunkDurationSeconds: Int = 5

    // Flow for emitting completed audio chunks
    private val _audioChunks = MutableSharedFlow<AudioChunk>(replay = 0, extraBufferCapacity = 10)
    val audioChunks: SharedFlow<AudioChunk> = _audioChunks

    // Flow for emitting raw audio frames (for wake word detection)
    private val _audioFrames = MutableSharedFlow<ShortArray>(replay = 0, extraBufferCapacity = 100)
    val audioFrames: SharedFlow<ShortArray> = _audioFrames

    // Sequence number for ordering
    private var sequenceNumber = 0

    /**
     * Audio chunk data containing WAV-formatted audio.
     */
    data class AudioChunk(
        val sequenceNumber: Int,
        val startTimestampMs: Long,
        val endTimestampMs: Long,
        val wavData: ByteArray,
        val sampleRate: Int = SAMPLE_RATE,
        val channels: Int = 1
    ) {
        override fun equals(other: Any?): Boolean {
            if (this === other) return true
            if (javaClass != other?.javaClass) return false
            other as AudioChunk
            return sequenceNumber == other.sequenceNumber
        }
        override fun hashCode(): Int = sequenceNumber
    }

    /**
     * Check if audio recording permission is granted.
     */
    fun hasPermission(): Boolean {
        return ContextCompat.checkSelfPermission(
            context,
            Manifest.permission.RECORD_AUDIO
        ) == PackageManager.PERMISSION_GRANTED
    }

    /**
     * Start audio recording.
     * Emits audio chunks every [chunkDurationSeconds] seconds.
     * @param audioSource Optional audio source (e.g. MediaRecorder.AudioSource.MIC). If 0, uses default logic.
     */
    fun start(scope: CoroutineScope, audioSource: Int = 0) {
        if (isRecording) {
            Log.w(TAG, "Already recording")
            return
        }

        if (!hasPermission()) {
            Log.e(TAG, "RECORD_AUDIO permission not granted")
            return
        }

        val minBufferSize = AudioRecord.getMinBufferSize(SAMPLE_RATE, CHANNEL_CONFIG, AUDIO_FORMAT)
        if (minBufferSize == AudioRecord.ERROR_BAD_VALUE || minBufferSize == AudioRecord.ERROR) {
            Log.e(TAG, "Invalid buffer size: $minBufferSize")
            return
        }

        // Use larger buffer for stability
        val bufferSize = maxOf(minBufferSize * 2, SAMPLE_RATE * 2) // At least 1 second

        try {
            val finalAudioSource = if (audioSource > 0) {
                audioSource
            } else {
                if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.N) {
                    MediaRecorder.AudioSource.UNPROCESSED
                } else {
                    MediaRecorder.AudioSource.MIC
                }
            }

            Log.i(TAG, "Initializing AudioRecord with source=$finalAudioSource, rate=$SAMPLE_RATE, buf=$bufferSize")

            audioRecord = AudioRecord(
                finalAudioSource,
                SAMPLE_RATE,
                CHANNEL_CONFIG,
                AUDIO_FORMAT,
                bufferSize
            )

            if (audioRecord?.state != AudioRecord.STATE_INITIALIZED) {
                Log.e(TAG, "AudioRecord failed to initialize")
                audioRecord?.release()
                audioRecord = null
                return
            }

            audioRecord?.startRecording()
            isRecording = true
            sequenceNumber = 0

            Log.i(TAG, "Audio recording started (chunk duration: ${chunkDurationSeconds}s)")

            recordingJob = scope.launch(Dispatchers.IO) {
                recordLoop()
            }

        } catch (e: SecurityException) {
            Log.e(TAG, "Security exception: ${e.message}")
        } catch (e: Exception) {
            Log.e(TAG, "Failed to start recording: ${e.message}")
        }
    }

    /**
     * Stop audio recording.
     */
    fun stop() {
        if (!isRecording) return

        isRecording = false
        recordingJob?.cancel()
        recordingJob = null

        try {
            audioRecord?.stop()
            audioRecord?.release()
        } catch (e: Exception) {
            Log.e(TAG, "Error stopping AudioRecord: ${e.message}")
        }
        audioRecord = null

        Log.i(TAG, "Audio recording stopped")
    }

    /**
     * Main recording loop.
     * Reads audio data, emits frames for wake word, and chunks for upload.
     */
    private suspend fun recordLoop() {
        val record = audioRecord ?: return
        coroutineScope {
        val frameBuffer = ShortArray(FRAME_SIZE)
        val chunkBuffer = ByteArrayOutputStream()
        var chunkStartTime = System.currentTimeMillis()
        val samplesPerChunk = SAMPLE_RATE * chunkDurationSeconds

        var samplesInChunk = 0

        while (isRecording && currentCoroutineContext().isActive) {
            val readResult = record.read(frameBuffer, 0, FRAME_SIZE)

            if (readResult > 0) {
                // Calculate RMS amplitude to verify audio is not silent
                var sum = 0.0
                for (i in 0 until readResult) {
                     val sample = frameBuffer[i].toInt()
                     sum += sample * sample
                }
                val rms = Math.sqrt(sum / readResult)
                if (rms < 1.0) {
                     // Log as INFO to ensure visibility on release builds/older devices
                     if (System.currentTimeMillis() % 2000 < 50) { // Throttle log
                        Log.i(TAG, "Silence detected! RMS: $rms")
                     }
                } else if (System.currentTimeMillis() % 10000 < 1000) { // Log occasionally
                     Log.i(TAG, "Audio Signal RMS: $rms")
                }

                launch {
                    val frame = frameBuffer.copyOfRange(0, readResult)
                    _audioFrames.emit(frame)
                }
                // Add to chunk buffer (convert short to bytes)
                for (i in 0 until readResult) {
                    val sample = frameBuffer[i].toInt()
                    chunkBuffer.write(sample and 0xFF)
                    chunkBuffer.write((sample shr 8) and 0xFF)
                }
                samplesInChunk += readResult

                // Check if chunk is complete
                if (samplesInChunk >= samplesPerChunk) {
                    val endTime = System.currentTimeMillis()
                    val pcmData = chunkBuffer.toByteArray()
                    val wavData = createWavFile(pcmData, SAMPLE_RATE, 1, 16)

                    val chunk = AudioChunk(
                        sequenceNumber = sequenceNumber++,
                        startTimestampMs = chunkStartTime,
                        endTimestampMs = endTime,
                        wavData = wavData
                    )

                    _audioChunks.tryEmit(chunk)
                    Log.d(TAG, "Audio chunk emitted: seq=${chunk.sequenceNumber}, size=${wavData.size}")

                    // Reset for next chunk
                    chunkBuffer.reset()
                    chunkStartTime = endTime
                    samplesInChunk = 0
                }

            } else if (readResult < 0) {
                Log.e(TAG, "AudioRecord read error: $readResult")
                delay(100) // Brief delay before retry
            }
                }
        }
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
        writeInt(header, 16, 16) // Subchunk1Size (16 for PCM)
        writeShort(header, 20, 1) // AudioFormat (1 = PCM)
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
