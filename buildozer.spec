[app]
title = Gestion Ferme
package.name = fermeagro
package.domain = org.ferme
source.dir = .
source.include_exts = py
source.exclude_dirs = tests, .github, bin, .buildozer
version = 1.0
requirements = python3,kivy==2.3.0,sqlite3,openpyxl,et_xmlfile
orientation = portrait
fullscreen = 0
android.archs = arm64-v8a, armeabi-v7a
android.api = 33
android.minapi = 21
android.accept_sdk_license = True
android.allow_backup = True

[buildozer]
log_level = 2
warn_on_root = 1
