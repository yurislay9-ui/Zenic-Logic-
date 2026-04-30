[app]

# (str) Title of your application
title = TITAN OMNISCALE X

# (str) Package name
package.name = titanomniscale

# (str) Package domain
package.domain = org.titan

# (str) Source directory
source.dir = .

# (list) Source files to include
source.include_exts = py,png,jpg,kv,atlas,yaml,json

# (list) Source patterns to include
source.include_patterns = src/*

# (str) Application version
version = 1.0.0

# (str) Requirements - SOLO paquetes compatibles con Android
# Kivy tiene recipe nativa en python-for-android
# numpy tiene recipe pero es pesado; pyyaml es pure-python
requirements = python3==3.11.5,kivy==2.3.0,pyyaml==6.0.1

# (str) Supported orientations
orientation = portrait

# (bool) Fullscreen mode
fullscreen = 0

# Android specific
android.permissions = INTERNET,ACCESS_NETWORK_STATE,ACCESS_WIFI_STATE
android.api = 33
android.minapi = 21
android.ndk = 25b
android.accept_sdk_license = True
android.archs = arm64-v8a, armeabi-v7a
android.copy_libs = 1
android.logcat_filters = *:S python:D

# Buildozer specific
log_level = 2
warn_on_root = 1
