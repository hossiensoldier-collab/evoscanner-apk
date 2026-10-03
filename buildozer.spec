[app]
title = EvoScanner
package.name = evoscanner
package.domain = org.evoscanner
source.dir = .
source.include_exts = py,png,jpg,kv,atlas,json,db
source.include_patterns = assets/*,data/*
version = 3.0.0
requirements = python3,kivy,requests,urllib3,certifi,chardet,idna
orientation = portrait
fullscreen = 0
android.permissions = INTERNET,ACCESS_NETWORK_STATE,WRITE_EXTERNAL_STORAGE,READ_EXTERNAL_STORAGE
android.api = 33
android.minapi = 24
android.ndk = 25b
android.archs = arm64-v8a, armeabi-v7a
android.allow_backup = True

[app:android]
android.logcat_filters = *:S python:D

[buildozer]
log_level = 2
warn_on_root = 0
