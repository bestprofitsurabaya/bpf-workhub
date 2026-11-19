#!/usr/bin/env bash
# Toolchain build Android Cordova. Ubah path di bawah bila lokasi berbeda,
# atau set variabel BPF_* sebelum memanggil build-android.sh.
export JAVA_HOME="${BPF_JAVA_HOME:-/home/it/android-tools/jdk/jdk-17.0.21+9}"
export ANDROID_SDK_ROOT="${BPF_ANDROID_SDK:-/home/it/android-tools/android-sdk}"
export ANDROID_HOME="$ANDROID_SDK_ROOT"
export GRADLE_HOME="${BPF_GRADLE_HOME:-/home/it/android-tools/gradle-8.14.2}"
export PATH="$JAVA_HOME/bin:$ANDROID_SDK_ROOT/cmdline-tools/latest/bin:$ANDROID_SDK_ROOT/platform-tools:$GRADLE_HOME/bin:$PATH"
export GRADLE_OPTS="-Dorg.gradle.jvmargs=-Xmx3g"
case ":$PATH:" in *":$HOME/.npm-global/bin:"*) ;; *) export PATH="$HOME/.npm-global/bin:$PATH" ;; esac
