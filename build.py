"""
Build script — packages Lndis AI Assistant as a standalone .exe

Usage:
  python build.py

Output:
  dist/LndisAI.exe
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PYTHON = sys.executable
PYINSTALLER = str(Path(PYTHON).parent / "Scripts" / "pyinstaller.exe")

if not Path(PYINSTALLER).exists():
    PYINSTALLER = None


def build():
    print("\n  Building Lndis AI Assistant .exe ...\n")

    import customtkinter
    ctk_path = Path(customtkinter.__file__).parent

    sep = ";"  # Windows path separator for --add-data

    args = [
        PYINSTALLER or PYTHON,
    ]
    if PYINSTALLER is None:
        args.extend(["-m", "PyInstaller"])

    args.extend([
        "--onefile",
        "--windowed",
        "--name", "LndisAI",

        # Runtime hook to fix imports
        "--runtime-hook", str(ROOT / "runtime_hook.py"),

        # Add project packages as data (preserves directory structure)
        "--add-data", f"{ROOT / 'core'}{sep}core",
        "--add-data", f"{ROOT / 'policy'}{sep}policy",
        "--add-data", f"{ROOT / 'tools'}{sep}tools",

        # Add customtkinter data (themes, fonts, etc.)
        "--add-data", f"{ctk_path}{sep}customtkinter",

        # Hidden imports for modules loaded dynamically
        "--hidden-import", "yaml",
        "--hidden-import", "customtkinter",
        "--hidden-import", "tkinter",

        # Paths to search for imports
        "--paths", str(ROOT),

        # Clean build
        "--clean",
        "--noconfirm",

        # Entry point
        str(ROOT / "ui" / "app.py"),
    ])

    # Add icon if exists
    icon = ROOT / "assets" / "icon.ico"
    if icon.exists():
        args.extend(["--icon", str(icon)])

    print(f"  Running PyInstaller...\n")

    result = subprocess.run(args, cwd=str(ROOT))

    if result.returncode == 0:
        exe_path = ROOT / "dist" / "LndisAI.exe"
        if exe_path.exists():
            size_mb = exe_path.stat().st_size / (1024 * 1024)
            print(f"\n  Build successful!")
            print(f"  Output: {exe_path}")
            print(f"  Size: {size_mb:.1f} MB\n")
        else:
            print(f"\n  Build completed but .exe not found at expected path.\n")
    else:
        print(f"\n  Build failed with code {result.returncode}\n")
        sys.exit(1)


if __name__ == "__main__":
    build()
