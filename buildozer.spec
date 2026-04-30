[app]

title = TITAN OMNISCALE X
package.name = titanomniscale
package.domain = org.titan
source.dir = .
source.include_exts = py,kv,json
source.exclude_dirs = tests,docs,data,__pycache__,src/api,src/config
source.exclude_patterns = mal_codigo*,auth*,*.md,*.kt,*.txt,.env*,.git*
version = 1.0.0
requirements = python3,kivy
orientation = portrait
fullscreen = 0

android.archs = arm64-v8a, armeabi-v7a
android.api = 33
android.minapi = 24
android.ndk = 25b
android.accept_sdk_license = True
android.enable_androidx = True
android.logcat_filters = *:S python:D

[buildozer]
log_level = 2
warn_on_root = 1
