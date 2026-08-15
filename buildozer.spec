[app]
title = Gestion Maintenance Delice
package.name = maintenancedelice
package.domain = org.delice
source.dir = .
source.main = main.py
source.include_exts = py,png,jpg,jpeg,ttf,db
version = 2.0
requirements = python3,kivy==2.3.1,fpdf2,plyer,Pillow,android
orientation = portrait
fullscreen = 0
# icon.filename = %(source.dir)s/icon.png
android.permissions = VIBRATE
android.api = 33
android.minapi = 21
android.ndk = 25b
android.archs = arm64-v8a,armeabi-v7a
android.accept_sdk_license = True
[buildozer]
log_level = 2
warn_on_root = 1
