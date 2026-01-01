package com.r2t4.app

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.util.Log
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.core.content.ContextCompat
import androidx.lifecycle.lifecycleScope
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import com.r2t4.app.service.CaptureService
import com.r2t4.app.settings.SettingsRepository
import com.r2t4.app.ui.MainScreen
import com.r2t4.app.ui.SettingsScreen
import com.r2t4.app.ui.theme.R2T4Theme
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch

/**
 * Main activity for R2T4.
 * Handles permissions, navigation, and service lifecycle.
 */
class MainActivity : ComponentActivity() {

    companion object {
        private const val TAG = "MainActivity"
    }

    private lateinit var settingsRepository: SettingsRepository

    // Permission launcher
    private val permissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions()
    ) { permissions ->
        val allGranted = permissions.all { it.value }
        Log.i(TAG, "Permissions result: $permissions, all granted: $allGranted")
        
        if (allGranted) {
            // Permissions granted, can start capture if needed
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        settingsRepository = SettingsRepository(this)

        // Request permissions
        requestRequiredPermissions()

        setContent {
            R2T4Theme {
                Surface(
                    modifier = Modifier.fillMaxSize(),
                    color = MaterialTheme.colorScheme.background
                ) {
                    R2T4App(settingsRepository)
                }
            }
        }
    }

    private fun requestRequiredPermissions() {
        val permissions = mutableListOf(
            Manifest.permission.RECORD_AUDIO,
            Manifest.permission.CAMERA
        )

        // Add notification permission for Android 13+
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            permissions.add(Manifest.permission.POST_NOTIFICATIONS)
        }

        val permissionsToRequest = permissions.filter {
            ContextCompat.checkSelfPermission(this, it) != PackageManager.PERMISSION_GRANTED
        }

        if (permissionsToRequest.isNotEmpty()) {
            permissionLauncher.launch(permissionsToRequest.toTypedArray())
        }
    }

    @Composable
    private fun R2T4App(settingsRepository: SettingsRepository) {
        val navController = rememberNavController()
        
        // Collect settings
        val settings by settingsRepository.settingsFlow.collectAsState(
            initial = SettingsRepository.Settings()
        )

        // Collect capture state
        val captureState by CaptureService.stateFlow.collectAsState()

        NavHost(navController = navController, startDestination = "main") {
            composable("main") {
                MainScreen(
                    state = captureState,
                    onStartCapture = { startCaptureService() },
                    onStopCapture = { stopCaptureService() },
                    onPushToTalk = { sendServiceAction(CaptureService.ACTION_PUSH_TO_TALK) },
                    onPromptDone = { sendServiceAction(CaptureService.ACTION_PROMPT_DONE) },
                    onPromptCancel = { sendServiceAction(CaptureService.ACTION_PROMPT_CANCEL) },
                    onOpenSettings = { navController.navigate("settings") }
                )
            }

            composable("settings") {
                SettingsScreen(
                    settings = settings,
                    onSettingsChanged = { newSettings ->
                        lifecycleScope.launch {
                            settingsRepository.updateSettings(newSettings)
                        }
                    },
                    onNavigateBack = { navController.popBackStack() }
                )
            }
        }
    }

    private fun startCaptureService() {
        val intent = Intent(this, CaptureService::class.java).apply {
            action = CaptureService.ACTION_START
        }
        
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            startForegroundService(intent)
        } else {
            startService(intent)
        }
    }

    private fun stopCaptureService() {
        sendServiceAction(CaptureService.ACTION_STOP)
    }

    private fun sendServiceAction(action: String) {
        val intent = Intent(this, CaptureService::class.java).apply {
            this.action = action
        }
        startService(intent)
    }
}
