"""Runtime hook: Ensure project modules are importable from the bundled EXE."""
import sys
import os

# When running as a PyInstaller bundle, add bundle dir to path
if getattr(sys, 'frozen', False):
    base = sys._MEIPASS
    if base not in sys.path:
        sys.path.insert(0, base)
