[app]
title = TITAN OMNISCALE X
package.name = titanomniscale
package.domain = org.titan
source.dir = .
source.include_exts = py,png,jpg,kv,atlas,yaml,json
source.exclude_patterns = tests/*,docs/*,*.md,.git/*,.github/*
requirements = python3,kivy==2.3.0,Cython<3.0
android.permissions = INTERNET,ACCESS_NETWORK_STATE,ACCESS_WIFI_STATE
android.api = 33
android.minapi = 24
android.ndk = 25b
android.enable_androidx = True
android.archs = arm64-v8a, armeabi-v7a
android.accept_sdk_license = True
p4a.branch = develop
log_level = 2
version = 2.0.0
