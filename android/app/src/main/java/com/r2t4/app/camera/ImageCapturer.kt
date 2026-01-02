package com.r2t4.app.camera

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.ImageFormat
import android.graphics.Matrix
import android.util.Log
import androidx.camera.core.*
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.core.content.ContextCompat
import androidx.lifecycle.LifecycleOwner
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.SharedFlow
import java.io.ByteArrayOutputStream
import java.util.concurrent.Executors
import kotlin.coroutines.resume
import kotlin.coroutines.suspendCoroutine

/**
 * ImageCapture handles periodic camera image capture using CameraX.
 * Captures images at configurable intervals and emits JPEG frames for upload.
 */
class ImageCapturer(private val context: Context) {

    companion object {
        private const val TAG = "ImageCapturer"
        const val DEFAULT_WIDTH = 1280
        const val DEFAULT_HEIGHT = 720
        const val DEFAULT_QUALITY = 70
    }

    private var cameraProvider: ProcessCameraProvider? = null
    private var imageCapture: ImageCapture? = null
    private var camera: Camera? = null
    private var captureJob: Job? = null
    private var isCapturing = false

    // Configuration
    var captureIntervalSeconds: Int = 2
    var imageWidth: Int = DEFAULT_WIDTH
    var imageHeight: Int = DEFAULT_HEIGHT
    var jpegQuality: Int = DEFAULT_QUALITY

    private val cameraExecutor = Executors.newSingleThreadExecutor()

    // Sequence number for ordering
    private var sequenceNumber = 0

    // Flow for emitting captured image frames
    private val _imageFrames = MutableSharedFlow<ImageFrame>(replay = 0, extraBufferCapacity = 10)
    val imageFrames: SharedFlow<ImageFrame> = _imageFrames

    /**
     * Image frame data containing JPEG-compressed image.
     */
    data class ImageFrame(
        val sequenceNumber: Int,
        val timestampMs: Long,
        val jpegData: ByteArray,
        val width: Int,
        val height: Int,
        val quality: Int
    ) {
        override fun equals(other: Any?): Boolean {
            if (this === other) return true
            if (javaClass != other?.javaClass) return false
            other as ImageFrame
            return sequenceNumber == other.sequenceNumber
        }
        override fun hashCode(): Int = sequenceNumber
    }

    /**
     * Check if camera permission is granted.
     */
    fun hasPermission(): Boolean {
        val granted = ContextCompat.checkSelfPermission(
            context,
            Manifest.permission.CAMERA
        ) == PackageManager.PERMISSION_GRANTED
        if (!granted) Log.w(TAG, "Camera permission CHECK failed")
        return granted
    }

    /**
     * Check if camera hardware is available.
     */
    fun hasCameraHardware(): Boolean {
        val hasFeature = context.packageManager.hasSystemFeature(PackageManager.FEATURE_CAMERA_ANY)
        if (!hasFeature) Log.w(TAG, "No camera hardware feature detected")
        return hasFeature
    }

    /**
     * Initialize the camera with the given lifecycle owner.
     * Uses the back camera.
     */
    suspend fun initialize(lifecycleOwner: LifecycleOwner): Boolean {
        Log.d(TAG, "Initializing camera...")
        
        if (!hasPermission()) {
            Log.e(TAG, "Camera permission not granted")
            return false
        }

        if (!hasCameraHardware()) {
            Log.e(TAG, "No camera hardware available")
            return false
        }

        return suspendCoroutine { continuation ->
            try {
                val cameraProviderFuture = ProcessCameraProvider.getInstance(context)
                cameraProviderFuture.addListener({
                    try {
                        cameraProvider = cameraProviderFuture.get()

                        // Set up image capture use case
                        imageCapture = ImageCapture.Builder()
                            .setCaptureMode(ImageCapture.CAPTURE_MODE_MINIMIZE_LATENCY)
                            .setTargetResolution(android.util.Size(imageWidth, imageHeight))
                            .setFlashMode(ImageCapture.FLASH_MODE_OFF)
                            .build()

                        // Select back camera
                        val cameraSelector = CameraSelector.DEFAULT_BACK_CAMERA

                        // Unbind any existing use cases
                        cameraProvider?.unbindAll()

                        // Bind use cases to camera
                        camera = cameraProvider?.bindToLifecycle(
                            lifecycleOwner,
                            cameraSelector,
                            imageCapture
                        )

                        Log.i(TAG, "Camera initialized successfully")
                        continuation.resume(true)

                    } catch (e: Exception) {
                        Log.e(TAG, "Failed to initialize camera: ${e.message}", e)
                        continuation.resume(false)
                    }
                }, ContextCompat.getMainExecutor(context))
            } catch (e: Exception) {
                 Log.e(TAG, "Failed to get camera provider: ${e.message}", e)
                 continuation.resume(false)
            }
        }
    }

    /**
     * Start periodic image capture.
     */
    fun startCapture(scope: CoroutineScope) {
        if (isCapturing) {
            Log.w(TAG, "Already capturing")
            return
        }

        if (imageCapture == null) {
            Log.e(TAG, "Camera not initialized - cannot start capture")
            return
        }

        isCapturing = true
        sequenceNumber = 0

        Log.i(TAG, "Image capture started (interval: ${captureIntervalSeconds}s)")

        captureJob = scope.launch(Dispatchers.Main) {
            while (isCapturing && isActive) {
                captureImage()
                delay(captureIntervalSeconds * 1000L)
            }
        }
    }

    /**
     * Stop image capture.
     */
    fun stopCapture() {
        if (!isCapturing) return

        isCapturing = false
        captureJob?.cancel()
        captureJob = null

        Log.i(TAG, "Image capture stopped")
    }

    /**
     * Capture a single image.
     */
    private suspend fun captureImage() {
        val capture = imageCapture ?: return

        suspendCoroutine { continuation ->
            capture.takePicture(
                cameraExecutor,
                object : ImageCapture.OnImageCapturedCallback() {
                    override fun onCaptureSuccess(image: ImageProxy) {
                        try {
                            val timestamp = System.currentTimeMillis()
                            val jpegData = imageProxyToJpeg(image)

                            if (jpegData != null) {
                                val frame = ImageFrame(
                                    sequenceNumber = sequenceNumber++,
                                    timestampMs = timestamp,
                                    jpegData = jpegData,
                                    width = imageWidth,
                                    height = imageHeight,
                                    quality = jpegQuality
                                )
                                _imageFrames.tryEmit(frame)
                                Log.d(TAG, "Image captured: seq=${frame.sequenceNumber}, size=${jpegData.size}")
                            } else {
                                Log.e(TAG, "Failed to convert image to JPEG")
                            }
                        } catch (e: Exception) {
                            Log.e(TAG, "Error processing captured image: ${e.message}")
                        } finally {
                            image.close()
                            continuation.resume(Unit)
                        }
                    }

                    override fun onError(exception: ImageCaptureException) {
                        Log.e(TAG, "Image capture failed: ${exception.message}", exception)
                        continuation.resume(Unit)
                    }
                }
            )
        }
    }

    /**
     * Convert ImageProxy to JPEG bytes with resizing.
     */
    private fun imageProxyToJpeg(image: ImageProxy): ByteArray? {
        return try {
            val buffer = image.planes[0].buffer
            val bytes = ByteArray(buffer.remaining())
            buffer.get(bytes)

            // Decode to bitmap for resizing
            val options = BitmapFactory.Options().apply {
                inSampleSize = calculateInSampleSize(image.width, image.height, imageWidth, imageHeight)
            }
            var bitmap = BitmapFactory.decodeByteArray(bytes, 0, bytes.size, options) ?: run {
                Log.e(TAG, "Failed to decode bitmap from bytes")
                 return null
            }

            // Rotate if needed based on image rotation
            val rotation = image.imageInfo.rotationDegrees
            if (rotation != 0) {
                val matrix = Matrix().apply { postRotate(rotation.toFloat()) }
                bitmap = Bitmap.createBitmap(bitmap, 0, 0, bitmap.width, bitmap.height, matrix, true)
            }

            // Scale to target size if needed, but PRESERVE ASPECT RATIO
            if (bitmap.width > imageWidth || bitmap.height > imageHeight) {
                val ratio = bitmap.width.toFloat() / bitmap.height.toFloat()
                var newWidth = imageWidth
                var newHeight = (newWidth / ratio).toInt()

                if (newHeight > imageHeight) {
                    newHeight = imageHeight
                    newWidth = (newHeight * ratio).toInt()
                }

                bitmap = Bitmap.createScaledBitmap(bitmap, newWidth, newHeight, true)
            }

            // Compress to JPEG
            val outputStream = ByteArrayOutputStream()
            bitmap.compress(Bitmap.CompressFormat.JPEG, jpegQuality, outputStream)
            outputStream.toByteArray()

        } catch (e: Exception) {
            Log.e(TAG, "Failed to convert image to JPEG: ${e.message}")
            null
        }
    }

    /**
     * Calculate appropriate sample size for BitmapFactory.
     */
    private fun calculateInSampleSize(
        sourceWidth: Int, sourceHeight: Int,
        targetWidth: Int, targetHeight: Int
    ): Int {
        var inSampleSize = 1
        if (sourceHeight > targetHeight || sourceWidth > targetWidth) {
            val halfHeight = sourceHeight / 2
            val halfWidth = sourceWidth / 2
            while ((halfHeight / inSampleSize) >= targetHeight &&
                   (halfWidth / inSampleSize) >= targetWidth) {
                inSampleSize *= 2
            }
        }
        return inSampleSize
    }

    /**
     * Release camera resources.
     */
    fun release() {
        stopCapture()
        cameraProvider?.unbindAll()
        cameraProvider = null
        imageCapture = null
        camera = null
        cameraExecutor.shutdown()
        Log.d(TAG, "Camera resources released")
    }
}
