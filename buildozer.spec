[app]
title = TITAN OMNISCALE X
package.name = titanomniscale
package.domain = org.titan
source.dir = .
source.include_exts = py,png,jpg,kv,atlas,yaml,json
source.include_patterns = src/*
version = 1.0.0
requirements = python3,kivy
orientation = portrait
fullscreen = 0

android.permissions = INTERNET,ACCESS_NETWORK_STATE,ACCESS_WIFI_STATE
android.api = 33
android.minapi = 21
android.ndk = 25b
android.accept_sdk_license = True
android.archs = arm64-v8a, armeabi-v7a
android.logcat_filters = *:S python:D

log_level = 2
warn_on_root = 1
