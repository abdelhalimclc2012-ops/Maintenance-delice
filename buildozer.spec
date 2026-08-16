[app]
title = Gestion Maintenance Delice
package.name = maintenancedelice
package.domain = org.delice
source.dir = .
source.main = main.py
source.include_exts = py,png,jpg,jpeg,ttf,db
version = 2.0
requirements = python3,kivy==2.3.1,fpdf2,fonttools,plyer,Pillow,android
orientation = portrait
fullscreen = 0
# icon.filename = %(source.dir)s/icon.png
android.permissions = VIBRATE
android.api = 33
android.minapi = 21
android.ndk = 25b
android.archs = arm64-v8a,armeabi-v7a
android.accept_sdk_license = True

# CORRECTIF : force la branche stable de python-for-android.
# La branche "develop" (utilisée par defaut par l'image Docker) exige
# Python 3.14, trop recent pour avoir des wheels PyPI compatibles pour
# fpdf2 et ses dependances -> ResolutionImpossible au build.
# "master" reste sur hostpython <=3.12, ou toutes les wheels existent.
p4a.branch = master

[buildozer]
log_level = 2
warn_on_root = 1
