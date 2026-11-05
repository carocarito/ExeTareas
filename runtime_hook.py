"""Rutas de DLL necesarias antes de importar PySide6 desde PyInstaller."""
import os
import sys

if getattr(sys, "frozen", False):
    root = sys._MEIPASS
    for folder in ("PySide6", "shiboken6"):
        candidate = os.path.join(root, folder)
        if os.path.isdir(candidate):
            os.add_dll_directory(candidate)
