package com.r2t4.app.ui

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import com.r2t4.app.settings.SettingsRepository

/**
 * Settings screen for configuring R2T4.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SettingsScreen(
    settings: SettingsRepository.Settings,
    onSettingsChanged: (SettingsRepository.Settings) -> Unit,
    onNavigateBack: () -> Unit
) {
    var serverAddress by remember(settings) { mutableStateOf(settings.serverAddress) }
    var deviceId by remember(settings) { mutableStateOf(settings.deviceId) }
    var audioChunkDuration by remember(settings) { mutableStateOf(settings.audioChunkDuration.toString()) }
    var photoInterval by remember(settings) { mutableStateOf(settings.photoInterval.toString()) }
    var photoQuality by remember(settings) { mutableStateOf(settings.photoQuality.toFloat()) }
    var promptTimeout by remember(settings) { mutableStateOf(settings.promptTimeout.toString()) }
    var pushToTalkMode by remember(settings) { mutableStateOf(settings.pushToTalkMode) }
    var porcupineAccessKey by remember(settings) { mutableStateOf(settings.porcupineAccessKey) }

    fun saveSettings() {
        onSettingsChanged(
            settings.copy(
                serverAddress = serverAddress,
                deviceId = deviceId,
                audioChunkDuration = audioChunkDuration.toIntOrNull() ?: 5,
                photoInterval = photoInterval.toIntOrNull() ?: 2,
                photoQuality = photoQuality.toInt(),
                promptTimeout = promptTimeout.toIntOrNull() ?: 15,
                pushToTalkMode = pushToTalkMode,
                porcupineAccessKey = porcupineAccessKey
            )
        )
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Settings") },
                navigationIcon = {
                    IconButton(onClick = {
                        saveSettings()
                        onNavigateBack()
                    }) {
                        Icon(Icons.Default.ArrowBack, contentDescription = "Back")
                    }
                }
            )
        }
    ) { paddingValues ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(paddingValues)
                .verticalScroll(rememberScrollState())
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp)
        ) {
            // Server section
            SectionHeader("Server Connection")
            
            OutlinedTextField(
                value = serverAddress,
                onValueChange = { serverAddress = it },
                label = { Text("Server Address") },
                placeholder = { Text("http://192.168.1.100:8080") },
                singleLine = true,
                modifier = Modifier.fillMaxWidth()
            )

            OutlinedTextField(
                value = deviceId,
                onValueChange = { deviceId = it },
                label = { Text("Device ID") },
                placeholder = { Text("my-tv-mate") },
                singleLine = true,
                modifier = Modifier.fillMaxWidth(),
                supportingText = { Text("Unique identifier for this device") }
            )

            Divider(modifier = Modifier.padding(vertical = 8.dp))

            // Audio section
            SectionHeader("Audio Capture")

            OutlinedTextField(
                value = audioChunkDuration,
                onValueChange = { audioChunkDuration = it },
                label = { Text("Chunk Duration (seconds)") },
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                singleLine = true,
                modifier = Modifier.fillMaxWidth(),
                supportingText = { Text("1-30 seconds, default: 5") }
            )

            OutlinedTextField(
                value = promptTimeout,
                onValueChange = { promptTimeout = it },
                label = { Text("Prompt Timeout (seconds)") },
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                singleLine = true,
                modifier = Modifier.fillMaxWidth(),
                supportingText = { Text("Maximum prompt recording time, default: 15") }
            )

            Divider(modifier = Modifier.padding(vertical = 8.dp))

            // Camera section
            SectionHeader("Camera Capture")

            OutlinedTextField(
                value = photoInterval,
                onValueChange = { photoInterval = it },
                label = { Text("Photo Interval (seconds)") },
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                singleLine = true,
                modifier = Modifier.fillMaxWidth(),
                supportingText = { Text("1-60 seconds, default: 2") }
            )

            Text(
                text = "Photo Quality: ${photoQuality.toInt()}%",
                style = MaterialTheme.typography.bodyMedium
            )
            Slider(
                value = photoQuality,
                onValueChange = { photoQuality = it },
                valueRange = 10f..100f,
                steps = 8,
                modifier = Modifier.fillMaxWidth()
            )

            Divider(modifier = Modifier.padding(vertical = 8.dp))

            // Wake word section
            SectionHeader("Wake Word Detection")

            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Column {
                    Text(
                        text = "Push-to-Talk Mode",
                        style = MaterialTheme.typography.bodyLarge
                    )
                    Text(
                        text = "Use button instead of wake word",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
                Switch(
                    checked = pushToTalkMode,
                    onCheckedChange = { pushToTalkMode = it }
                )
            }

            if (!pushToTalkMode) {
                OutlinedTextField(
                    value = porcupineAccessKey,
                    onValueChange = { porcupineAccessKey = it },
                    label = { Text("Picovoice Access Key") },
                    placeholder = { Text("Enter your API key") },
                    singleLine = true,
                    visualTransformation = PasswordVisualTransformation(),
                    modifier = Modifier.fillMaxWidth(),
                    supportingText = { 
                        Text("Get key from console.picovoice.ai") 
                    }
                )

                Card(
                    colors = CardDefaults.cardColors(
                        containerColor = MaterialTheme.colorScheme.primaryContainer
                    ),
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Column(modifier = Modifier.padding(16.dp)) {
                        Text(
                            text = "Wake Word: \"Porcupine\"",
                            style = MaterialTheme.typography.titleSmall
                        )
                        Text(
                            text = "Say \"Porcupine\" to start a prompt. Custom wake words require training at Picovoice Console.",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onPrimaryContainer
                        )
                    }
                }
            }

            Spacer(modifier = Modifier.height(32.dp))

            // Save button
            Button(
                onClick = {
                    saveSettings()
                    onNavigateBack()
                },
                modifier = Modifier.fillMaxWidth()
            ) {
                Text("Save Settings")
            }
        }
    }
}

@Composable
private fun SectionHeader(title: String) {
    Text(
        text = title,
        style = MaterialTheme.typography.titleMedium,
        color = MaterialTheme.colorScheme.primary
    )
}
