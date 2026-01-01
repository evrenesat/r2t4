package com.r2t4.app.settings

import android.content.Context
import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.*
import androidx.datastore.preferences.preferencesDataStore
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.catch
import kotlinx.coroutines.flow.map
import java.io.IOException

/**
 * Settings repository using DataStore for persistent settings storage.
 * All settings survive app updates.
 */
class SettingsRepository(private val context: Context) {

    companion object {
        // DataStore instance
        private val Context.dataStore: DataStore<Preferences> by preferencesDataStore(name = "r2t4_settings")

        // Settings keys
        private val KEY_SERVER_ADDRESS = stringPreferencesKey("server_address")
        private val KEY_DEVICE_ID = stringPreferencesKey("device_id")
        private val KEY_AUDIO_CHUNK_DURATION = intPreferencesKey("audio_chunk_duration")
        private val KEY_PHOTO_INTERVAL = intPreferencesKey("photo_interval")
        private val KEY_PHOTO_QUALITY = intPreferencesKey("photo_quality")
        private val KEY_PROMPT_TIMEOUT = intPreferencesKey("prompt_timeout")
        private val KEY_PUSH_TO_TALK_MODE = booleanPreferencesKey("push_to_talk_mode")
        private val KEY_PORCUPINE_ACCESS_KEY = stringPreferencesKey("porcupine_access_key")
    }

    /**
     * App settings data class.
     */
    data class Settings(
        val serverAddress: String = "http://192.168.1.100:8080",
        val deviceId: String = "my-tv-mate",
        val audioChunkDuration: Int = 5,      // seconds
        val photoInterval: Int = 2,            // seconds
        val photoQuality: Int = 70,            // 0-100
        val promptTimeout: Int = 15,           // seconds
        val pushToTalkMode: Boolean = false,   // fallback if wake word fails
        val porcupineAccessKey: String = ""    // Picovoice API key
    )

    /**
     * Flow of current settings, emits on any change.
     */
    val settingsFlow: Flow<Settings> = context.dataStore.data
        .catch { exception ->
            if (exception is IOException) {
                emit(emptyPreferences())
            } else {
                throw exception
            }
        }
        .map { prefs ->
            Settings(
                serverAddress = prefs[KEY_SERVER_ADDRESS] ?: Settings().serverAddress,
                deviceId = prefs[KEY_DEVICE_ID] ?: Settings().deviceId,
                audioChunkDuration = prefs[KEY_AUDIO_CHUNK_DURATION] ?: Settings().audioChunkDuration,
                photoInterval = prefs[KEY_PHOTO_INTERVAL] ?: Settings().photoInterval,
                photoQuality = prefs[KEY_PHOTO_QUALITY] ?: Settings().photoQuality,
                promptTimeout = prefs[KEY_PROMPT_TIMEOUT] ?: Settings().promptTimeout,
                pushToTalkMode = prefs[KEY_PUSH_TO_TALK_MODE] ?: Settings().pushToTalkMode,
                porcupineAccessKey = prefs[KEY_PORCUPINE_ACCESS_KEY] ?: Settings().porcupineAccessKey
            )
        }

    /**
     * Update server address.
     */
    suspend fun setServerAddress(value: String) {
        context.dataStore.edit { prefs ->
            prefs[KEY_SERVER_ADDRESS] = value
        }
    }

    /**
     * Update device ID.
     */
    suspend fun setDeviceId(value: String) {
        context.dataStore.edit { prefs ->
            prefs[KEY_DEVICE_ID] = value
        }
    }

    /**
     * Update audio chunk duration (seconds).
     */
    suspend fun setAudioChunkDuration(value: Int) {
        context.dataStore.edit { prefs ->
            prefs[KEY_AUDIO_CHUNK_DURATION] = value.coerceIn(1, 30)
        }
    }

    /**
     * Update photo interval (seconds).
     */
    suspend fun setPhotoInterval(value: Int) {
        context.dataStore.edit { prefs ->
            prefs[KEY_PHOTO_INTERVAL] = value.coerceIn(1, 60)
        }
    }

    /**
     * Update photo quality (0-100).
     */
    suspend fun setPhotoQuality(value: Int) {
        context.dataStore.edit { prefs ->
            prefs[KEY_PHOTO_QUALITY] = value.coerceIn(10, 100)
        }
    }

    /**
     * Update prompt timeout (seconds).
     */
    suspend fun setPromptTimeout(value: Int) {
        context.dataStore.edit { prefs ->
            prefs[KEY_PROMPT_TIMEOUT] = value.coerceIn(5, 60)
        }
    }

    /**
     * Update push-to-talk mode.
     */
    suspend fun setPushToTalkMode(value: Boolean) {
        context.dataStore.edit { prefs ->
            prefs[KEY_PUSH_TO_TALK_MODE] = value
        }
    }

    /**
     * Update Porcupine access key.
     */
    suspend fun setPorcupineAccessKey(value: String) {
        context.dataStore.edit { prefs ->
            prefs[KEY_PORCUPINE_ACCESS_KEY] = value
        }
    }

    /**
     * Update all settings at once.
     */
    suspend fun updateSettings(settings: Settings) {
        context.dataStore.edit { prefs ->
            prefs[KEY_SERVER_ADDRESS] = settings.serverAddress
            prefs[KEY_DEVICE_ID] = settings.deviceId
            prefs[KEY_AUDIO_CHUNK_DURATION] = settings.audioChunkDuration
            prefs[KEY_PHOTO_INTERVAL] = settings.photoInterval
            prefs[KEY_PHOTO_QUALITY] = settings.photoQuality
            prefs[KEY_PROMPT_TIMEOUT] = settings.promptTimeout
            prefs[KEY_PUSH_TO_TALK_MODE] = settings.pushToTalkMode
            prefs[KEY_PORCUPINE_ACCESS_KEY] = settings.porcupineAccessKey
        }
    }
}
