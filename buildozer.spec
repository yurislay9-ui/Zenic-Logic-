[app]

title = TITAN OMNISCALE X
package.name = titanomniscale
package.domain = org.titan
source.dir = .
source.include_exts = py,png,jpg,kv,atlas,yaml,json
version = 1.0.0
requirements = python3,kivy,pyjnius
orientation = portrait
fullscreen = 0

android.permissions = INTERNET
android.api = 33
android.minapi = 21
android.ndk = 25b
android.accept_sdk_license = True
android.archs = arm64-v8a
android.logcat_filters = *:S python:D

p4a.branch = develop
log_level = 2
warn_on_root = 1

# Forzar receta pyjnius
android.gradle_dependencies = ''
