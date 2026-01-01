package com.r2t4.app.grpc

import android.util.Log
import com.connectrpc.ConnectException
import com.connectrpc.ProtocolClientConfig
import com.connectrpc.extensions.GoogleJavaLiteProtobufStrategy
import com.connectrpc.impl.ProtocolClient
import com.connectrpc.okhttp.ConnectOkHttpClient
import com.connectrpc.protocols.NetworkProtocol
import com.r2t4.app.audio.AudioRecorder
import com.r2t4.app.audio.PromptRecorder
import com.r2t4.app.camera.ImageCapturer
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.OkHttpClient
import java.util.UUID
import java.util.concurrent.TimeUnit

/**
 * R2T4Client handles all gRPC communication with the server using Connect-Kotlin.
 * Provides methods for uploading audio chunks, images, and prompts.
 */
class R2T4Client {

    companion object {
        private const val TAG = "R2T4Client"
    }

    private var client: ProtocolClient? = null
    private var serverAddress: String = ""

    // Upload service client (will be generated from proto)
    // For MVP1, we'll use raw HTTP until proto generation is set up

    /**
     * Initialize the client with the server address.
     */
    fun initialize(serverAddress: String) {
        this.serverAddress = serverAddress

        val okHttpClient = OkHttpClient.Builder()
            .connectTimeout(30, TimeUnit.SECONDS)
            .readTimeout(30, TimeUnit.SECONDS)
            .writeTimeout(30, TimeUnit.SECONDS)
            .build()

        client = ProtocolClient(
            httpClient = ConnectOkHttpClient(okHttpClient),
            ProtocolClientConfig(
                host = serverAddress,
                serializationStrategy = GoogleJavaLiteProtobufStrategy(),
                networkProtocol = NetworkProtocol.CONNECT,
            )
        )

        Log.i(TAG, "R2T4 client initialized with server: $serverAddress")
    }

    /**
     * Check if client is initialized.
     */
    fun isInitialized(): Boolean = client != null

    /**
     * Upload an audio chunk to the server.
     * Returns the acknowledgment ID on success, null on failure.
     */
    suspend fun uploadAudioChunk(
        deviceId: String,
        chunk: AudioRecorder.AudioChunk
    ): UploadResult = withContext(Dispatchers.IO) {
        try {
            // For MVP1, use direct HTTP POST until proto client is generated
            val okHttpClient = OkHttpClient.Builder()
                .connectTimeout(30, TimeUnit.SECONDS)
                .readTimeout(30, TimeUnit.SECONDS)
                .writeTimeout(30, TimeUnit.SECONDS)
                .build()

            val request = okhttp3.Request.Builder()
                .url("$serverAddress/r2t4.v1.UploadService/UploadAudioChunk")
                .addHeader("Content-Type", "application/connect+proto")
                .post(createAudioChunkRequest(deviceId, chunk))
                .build()

            val response = okHttpClient.newCall(request).execute()
            
            if (response.isSuccessful) {
                val ackId = "ack-${UUID.randomUUID()}" // Parse from response in real impl
                Log.d(TAG, "Audio chunk uploaded: seq=${chunk.sequenceNumber}, ack=$ackId")
                UploadResult.Success(ackId)
            } else {
                Log.e(TAG, "Audio upload failed: ${response.code}")
                UploadResult.Error("HTTP ${response.code}: ${response.message}")
            }
        } catch (e: ConnectException) {
            Log.e(TAG, "Connect error uploading audio: ${e.message}")
            UploadResult.Error(e.message ?: "Connect error")
        } catch (e: Exception) {
            Log.e(TAG, "Error uploading audio: ${e.message}")
            UploadResult.Error(e.message ?: "Unknown error")
        }
    }

    /**
     * Upload an image frame to the server.
     */
    suspend fun uploadImageFrame(
        deviceId: String,
        frame: ImageCapturer.ImageFrame
    ): UploadResult = withContext(Dispatchers.IO) {
        try {
            val okHttpClient = OkHttpClient.Builder()
                .connectTimeout(30, TimeUnit.SECONDS)
                .readTimeout(30, TimeUnit.SECONDS)
                .writeTimeout(30, TimeUnit.SECONDS)
                .build()

            val request = okhttp3.Request.Builder()
                .url("$serverAddress/r2t4.v1.UploadService/UploadImageFrame")
                .addHeader("Content-Type", "application/connect+proto")
                .post(createImageFrameRequest(deviceId, frame))
                .build()

            val response = okHttpClient.newCall(request).execute()
            
            if (response.isSuccessful) {
                val ackId = "ack-${UUID.randomUUID()}"
                Log.d(TAG, "Image frame uploaded: seq=${frame.sequenceNumber}, ack=$ackId")
                UploadResult.Success(ackId)
            } else {
                Log.e(TAG, "Image upload failed: ${response.code}")
                UploadResult.Error("HTTP ${response.code}: ${response.message}")
            }
        } catch (e: Exception) {
            Log.e(TAG, "Error uploading image: ${e.message}")
            UploadResult.Error(e.message ?: "Unknown error")
        }
    }

    /**
     * Upload prompt audio chunk (streaming).
     */
    suspend fun uploadPromptChunk(
        deviceId: String,
        chunk: PromptRecorder.PromptChunk
    ): UploadResult = withContext(Dispatchers.IO) {
        try {
            // For MVP1, simplified implementation
            // Real implementation would use streaming RPC
            val okHttpClient = OkHttpClient.Builder()
                .connectTimeout(30, TimeUnit.SECONDS)
                .readTimeout(30, TimeUnit.SECONDS)
                .writeTimeout(30, TimeUnit.SECONDS)
                .build()

            val request = okhttp3.Request.Builder()
                .url("$serverAddress/r2t4.v1.PromptService/SubmitPrompt")
                .addHeader("Content-Type", "application/connect+proto")
                .post(createPromptChunkRequest(deviceId, chunk))
                .build()

            val response = okHttpClient.newCall(request).execute()
            
            if (response.isSuccessful) {
                Log.d(TAG, "Prompt chunk uploaded: prompt=${chunk.promptId}, index=${chunk.chunkIndex}, final=${chunk.isFinal}")
                UploadResult.Success(chunk.promptId)
            } else {
                Log.e(TAG, "Prompt upload failed: ${response.code}")
                UploadResult.Error("HTTP ${response.code}: ${response.message}")
            }
        } catch (e: Exception) {
            Log.e(TAG, "Error uploading prompt: ${e.message}")
            UploadResult.Error(e.message ?: "Unknown error")
        }
    }

    /**
     * Get response for a submitted prompt.
     */
    suspend fun getPromptResponse(
        deviceId: String,
        promptId: String
    ): PromptResponse = withContext(Dispatchers.IO) {
        try {
            val okHttpClient = OkHttpClient.Builder()
                .connectTimeout(30, TimeUnit.SECONDS)
                .readTimeout(30, TimeUnit.SECONDS)
                .build()

            val request = okhttp3.Request.Builder()
                .url("$serverAddress/r2t4.v1.PromptService/GetPromptResponse")
                .addHeader("Content-Type", "application/connect+proto")
                .post(createGetPromptRequest(deviceId, promptId))
                .build()

            val response = okHttpClient.newCall(request).execute()
            
            if (response.isSuccessful) {
                // Parse response - simplified for MVP1
                val body = response.body?.string() ?: ""
                Log.d(TAG, "Got prompt response for $promptId")
                PromptResponse.Completed(
                    promptId = promptId,
                    responseText = "Response received at ${System.currentTimeMillis()}",
                    processedAtMs = System.currentTimeMillis()
                )
            } else {
                PromptResponse.Error("HTTP ${response.code}")
            }
        } catch (e: Exception) {
            Log.e(TAG, "Error getting prompt response: ${e.message}")
            PromptResponse.Error(e.message ?: "Unknown error")
        }
    }

    // Placeholder request body creators (real implementation would use protobuf)
    private fun createAudioChunkRequest(deviceId: String, chunk: AudioRecorder.AudioChunk): okhttp3.RequestBody {
        // In real implementation, serialize protobuf message
        return okhttp3.RequestBody.create(
            okhttp3.MediaType.parse("application/octet-stream"),
            chunk.wavData
        )
    }

    private fun createImageFrameRequest(deviceId: String, frame: ImageCapturer.ImageFrame): okhttp3.RequestBody {
        return okhttp3.RequestBody.create(
            okhttp3.MediaType.parse("application/octet-stream"),
            frame.jpegData
        )
    }

    private fun createPromptChunkRequest(deviceId: String, chunk: PromptRecorder.PromptChunk): okhttp3.RequestBody {
        return okhttp3.RequestBody.create(
            okhttp3.MediaType.parse("application/octet-stream"),
            chunk.audioData
        )
    }

    private fun createGetPromptRequest(deviceId: String, promptId: String): okhttp3.RequestBody {
        return okhttp3.RequestBody.create(
            okhttp3.MediaType.parse("application/json"),
            """{"device_id":"$deviceId","prompt_id":"$promptId"}"""
        )
    }

    /**
     * Result of an upload operation.
     */
    sealed class UploadResult {
        data class Success(val ackId: String) : UploadResult()
        data class Error(val message: String) : UploadResult()
    }

    /**
     * Result of getting a prompt response.
     */
    sealed class PromptResponse {
        data class Completed(
            val promptId: String,
            val responseText: String,
            val processedAtMs: Long
        ) : PromptResponse()
        data class Processing(val promptId: String, val queuePosition: Int) : PromptResponse()
        data class Error(val message: String) : PromptResponse()
    }
}
