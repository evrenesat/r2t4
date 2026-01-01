# Add project specific ProGuard rules here.
# By default, the flags in this file are appended to flags specified
# in /sdk/tools/proguard/proguard-android.txt

# Keep Connect-Kotlin classes
-keep class com.connectrpc.** { *; }
-keepclassmembers class * extends com.google.protobuf.GeneratedMessageLite {
    <fields>;
}

# Keep Porcupine
-keep class ai.picovoice.** { *; }

# Keep proto generated classes
-keep class com.r2t4.proto.** { *; }
