M[app]
title = Gestion Maintenance Delice
package.name = maintenancedelice
package.domain = org.delice

source.dir = .
source.main = main.py
source.include_exts = py,png,jpg,jpeg,ttf,db

version = 2.0

requirements = python3,cython==0.29.33,kivy==2.3.0,fpdf2,plyer

orientation = portrait
fullscreen = 0

icon.filename = %(source.dir)s/icon.png

# Permissions Android nécessaires (stockage pour export PDF/CSV, vibration)
android.permissions = WRITE_EXTERNAL_STORAGE,READ_EXTERNAL_STORAGE,VIBRATE

android.api = 34
android.minapi = 21
android.ndk = 25b
android.archs = arm64-v8a,armeabi-v7a
android.accept_sdk_license = True

# Nécessaire pour l'accès fichiers sur Android 11+ (scoped storage)
android.allow_backup = True

[buildozer]
log_level = 2
warn_on_root = 1
