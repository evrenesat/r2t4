package com.r2t4.app.ui

import androidx.compose.animation.animateColorAsState
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.r2t4.app.service.CaptureService
import com.r2t4.app.ui.theme.StatusColors
import kotlinx.coroutines.launch
import java.text.SimpleDateFormat
import java.util.*

/**
 * Main screen showing capture status and log output.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun MainScreen(
    state: CaptureService.CaptureState,
    onStartCapture: () -> Unit,
    onStopCapture: () -> Unit,
    onPushToTalk: () -> Unit,
    onPromptDone: () -> Unit,
    onPromptCancel: () -> Unit,
    onOpenSettings: () -> Unit
) {
    val listState = rememberLazyListState()
    val coroutineScope = rememberCoroutineScope()

    // Auto-scroll to bottom when new messages arrive
    LaunchedEffect(state.logMessages.size) {
        if (state.logMessages.isNotEmpty()) {
            coroutineScope.launch {
                listState.animateScrollToItem(state.logMessages.size - 1)
            }
        }
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text("📺 R2T4", fontWeight = FontWeight.Bold)
                        Spacer(Modifier.width(12.dp))
                        StatusIndicator(state)
                    }
                },
                actions = {
                    IconButton(onClick = onOpenSettings) {
                        Icon(Icons.Default.Settings, contentDescription = "Settings")
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = MaterialTheme.colorScheme.background
                )
            )
        },
        bottomBar = {
            BottomControls(
                state = state,
                onStartCapture = onStartCapture,
                onStopCapture = onStopCapture,
                onPushToTalk = onPushToTalk,
                onPromptDone = onPromptDone,
                onPromptCancel = onPromptCancel
            )
        }
    ) { paddingValues ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(paddingValues)
        ) {
            // Stats bar
            if (state.isRunning) {
                StatsBar(state)
            }

            // Log viewer
            LazyColumn(
                state = listState,
                modifier = Modifier
                    .fillMaxSize()
                    .padding(horizontal = 16.dp),
                verticalArrangement = Arrangement.spacedBy(4.dp)
            ) {
                if (state.logMessages.isEmpty()) {
                    item {
                        Box(
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(vertical = 48.dp),
                            contentAlignment = Alignment.Center
                        ) {
                            Column(horizontalAlignment = Alignment.CenterHorizontally) {
                                Text(
                                    "👋",
                                    fontSize = 48.sp
                                )
                                Spacer(Modifier.height(16.dp))
                                Text(
                                    "Welcome to R2T4",
                                    style = MaterialTheme.typography.headlineSmall,
                                    color = MaterialTheme.colorScheme.onSurface
                                )
                                Text(
                                    "Press Start to begin capturing",
                                    style = MaterialTheme.typography.bodyMedium,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant
                                )
                            }
                        }
                    }
                }

                items(state.logMessages) { entry ->
                    LogEntryRow(entry)
                }
            }
        }
    }
}

@Composable
private fun StatusIndicator(state: CaptureService.CaptureState) {
    val color by animateColorAsState(
        targetValue = when {
            state.isPrompting -> StatusColors.prompting
            state.isRunning -> StatusColors.recording
            else -> StatusColors.inactive
        },
        label = "status_color"
    )

    val text = when {
        state.isPrompting -> "Listening..."
        state.isRunning -> "Recording"
        else -> "Stopped"
    }

    Row(
        verticalAlignment = Alignment.CenterVertically,
        modifier = Modifier
            .background(
                color = color.copy(alpha = 0.2f),
                shape = RoundedCornerShape(16.dp)
            )
            .padding(horizontal = 12.dp, vertical = 6.dp)
    ) {
        Box(
            modifier = Modifier
                .size(8.dp)
                .clip(CircleShape)
                .background(color)
        )
        Spacer(Modifier.width(8.dp))
        Text(
            text = text,
            style = MaterialTheme.typography.labelMedium,
            color = color
        )
    }
}

@Composable
private fun StatsBar(state: CaptureService.CaptureState) {
    val stats = state.uploadStats
    
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .background(MaterialTheme.colorScheme.surfaceVariant)
            .padding(horizontal = 16.dp, vertical = 8.dp),
        horizontalArrangement = Arrangement.SpaceBetween
    ) {
        StatItem("🎤", stats["audioChunksSent"] ?: 0)
        StatItem("📷", stats["imagesSent"] ?: 0)
        StatItem("💬", stats["promptChunksSent"] ?: 0)
        StatItem("📤", stats["pendingCount"] ?: 0)
    }
}

@Composable
private fun StatItem(emoji: String, count: Int) {
    Row(verticalAlignment = Alignment.CenterVertically) {
        Text(emoji, fontSize = 16.sp)
        Spacer(Modifier.width(4.dp))
        Text(
            count.toString(),
            style = MaterialTheme.typography.labelMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant
        )
    }
}

@Composable
private fun LogEntryRow(entry: CaptureService.LogEntry) {
    val backgroundColor = when (entry.type) {
        CaptureService.LogType.ERROR -> MaterialTheme.colorScheme.error.copy(alpha = 0.1f)
        CaptureService.LogType.WARNING -> Color(0xFFF59E0B).copy(alpha = 0.1f)
        CaptureService.LogType.RESPONSE -> MaterialTheme.colorScheme.primary.copy(alpha = 0.1f)
        else -> Color.Transparent
    }

    val textColor = when (entry.type) {
        CaptureService.LogType.ERROR -> MaterialTheme.colorScheme.error
        CaptureService.LogType.WARNING -> Color(0xFFF59E0B)
        CaptureService.LogType.RESPONSE -> MaterialTheme.colorScheme.primary
        else -> MaterialTheme.colorScheme.onSurface
    }

    val timeFormat = SimpleDateFormat("HH:mm:ss", Locale.getDefault())

    Row(
        modifier = Modifier
            .fillMaxWidth()
            .background(backgroundColor, RoundedCornerShape(4.dp))
            .padding(horizontal = 8.dp, vertical = 4.dp)
    ) {
        Text(
            text = timeFormat.format(Date(entry.timestamp)),
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            fontFamily = FontFamily.Monospace,
            modifier = Modifier.width(70.dp)
        )
        Text(
            text = entry.message,
            style = MaterialTheme.typography.bodyMedium,
            color = textColor
        )
    }
}

@Composable
private fun BottomControls(
    state: CaptureService.CaptureState,
    onStartCapture: () -> Unit,
    onStopCapture: () -> Unit,
    onPushToTalk: () -> Unit,
    onPromptDone: () -> Unit,
    onPromptCancel: () -> Unit
) {
    Surface(
        color = MaterialTheme.colorScheme.surface,
        tonalElevation = 4.dp
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp),
            horizontalArrangement = Arrangement.SpaceEvenly,
            verticalAlignment = Alignment.CenterVertically
        ) {
            if (state.isPrompting) {
                // Prompt mode controls
                Button(
                    onClick = onPromptCancel,
                    colors = ButtonDefaults.buttonColors(
                        containerColor = MaterialTheme.colorScheme.error
                    )
                ) {
                    Icon(Icons.Default.Close, contentDescription = null)
                    Spacer(Modifier.width(8.dp))
                    Text("Cancel")
                }

                Button(
                    onClick = onPromptDone,
                    colors = ButtonDefaults.buttonColors(
                        containerColor = StatusColors.recording
                    )
                ) {
                    Icon(Icons.Default.Send, contentDescription = null)
                    Spacer(Modifier.width(8.dp))
                    Text("Done")
                }
            } else if (state.isRunning) {
                // Running mode controls
                Button(
                    onClick = onStopCapture,
                    colors = ButtonDefaults.buttonColors(
                        containerColor = MaterialTheme.colorScheme.error
                    )
                ) {
                    Icon(Icons.Default.Stop, contentDescription = null)
                    Spacer(Modifier.width(8.dp))
                    Text("Stop")
                }

                // Push-to-talk button (always available as fallback)
                FilledTonalButton(
                    onClick = onPushToTalk,
                    modifier = Modifier.size(64.dp),
                    shape = CircleShape
                ) {
                    Icon(
                        Icons.Default.Mic,
                        contentDescription = "Push to Talk",
                        modifier = Modifier.size(32.dp)
                    )
                }
            } else {
                // Stopped mode
                Button(
                    onClick = onStartCapture,
                    colors = ButtonDefaults.buttonColors(
                        containerColor = StatusColors.recording
                    ),
                    modifier = Modifier.height(56.dp)
                ) {
                    Icon(Icons.Default.PlayArrow, contentDescription = null)
                    Spacer(Modifier.width(8.dp))
                    Text("Start Capture", fontWeight = FontWeight.Bold)
                }
            }
        }
    }
}
