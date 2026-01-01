package com.r2t4.app

import android.app.Application
import android.app.NotificationChannel
import android.app.NotificationManager
import android.os.Build
import android.util.Log

/**
 * R2T4 Application class.
 * Initializes app-wide resources like notification channels.
 */
class R2T4Application : Application() {

    companion object {
        private const val TAG = "R2T4Application"
        const val NOTIFICATION_CHANNEL_ID = "r2t4_capture"
    }

    override fun onCreate() {
        super.onCreate()
        Log.i(TAG, "R2T4 Application starting...")
        createNotificationChannel()
    }

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                NOTIFICATION_CHANNEL_ID,
                getString(R.string.notification_channel_name),
                NotificationManager.IMPORTANCE_LOW
            ).apply {
                description = getString(R.string.notification_channel_description)
                setShowBadge(false)
            }

            val notificationManager = getSystemService(NotificationManager::class.java)
            notificationManager.createNotificationChannel(channel)
            Log.d(TAG, "Notification channel created")
        }
    }
}
