[app]

title = TITAN OMNISCALE X
package.name = titanomniscale
package.domain = org.titan
source.dir = .
source.include_exts = py,kv
version = 1.0.0
requirements = python3,kivy
orientation = portrait
fullscreen = 0

android.archs = arm64-v8a
android.api = 33
android.minapi = 24
android.ndk = 25b
android.accept_sdk_license = True
android.enable_androidx = True

p4a.branch = master

[buildozer]
log_level = 2
warn_on_root = 1
