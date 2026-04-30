[app]

# (str) Title of your application
title = TITAN OMNISCALE X

# (str) Package name
package.name = titanomniscale

# (str) Package domain (needed for android/ios packaging)
package.domain = org.titan

# (str) Source directory where the main python script lives
source.dir = .

# (list) Source files to include (let empty to include all files)
source.include_exts = py,png,jpg,kv,atlas,yaml,json

# (list) List of inclusions using pattern matching
source.include_patterns = src/*

# (list) Source files to exclude
source.exclude_exts = spec,md,txt

# (str) Application versioning
version = 1.0.0

# (str) Requirements - only packages compatible with Android/ARM
# fastapi/uvicorn/fastembed/tree-sitter-languages excluded - no ARM builds
requirements = python3==3.11.5,kivy==2.3.0,pydantic==2.7.1,pyyaml==6.0.1,numpy==1.26.4,httpx==0.27.0,aiofiles==23.2.1,python-constraint==1.4.0

# (str) Supported orientations
orientation = portrait

# (bool) Indicate if the application should be fullscreen
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
