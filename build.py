"""
Build script — packages Lndis AI Assistant as a standalone app.

Usage:
  python build.py

Output:
  dist/LndisAI-v<version>.exe
"""

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PYTHON = sys.executable


def read_version() -> str:
    version_file = ROOT / "VERSION"
    if version_file.exists():
        return version_file.read_text(encoding="utf-8").strip() or "0.1"
    return "0.1"


def build() -> None:
    version = read_version()
    app_name = f"LndisAI-v{version}"
    print(f"\n  Building {app_name} ...\n")

    try:
        import customtkinter
    except Exception as exc:
        print(f"  Missing dependency: customtkinter ({exc})")
        print("  Install requirements first, then retry.")
        sys.exit(1)

    ctk_path = Path(customtkinter.__file__).parent
    pyinstaller_cmd = shutil.which("pyinstaller")
    sep = ";" if sys.platform.startswith("win") else ":"

    args = [pyinstaller_cmd or PYTHON]
    if pyinstaller_cmd is None:
        args.extend(["-m", "PyInstaller"])

    args.extend([
        "--onefile",
        "--windowed",
        "--name", app_name,
        "--runtime-hook", str(ROOT / "runtime_hook.py"),
        "--add-data", f"{ROOT / 'core'}{sep}core",
        "--add-data", f"{ROOT / 'policy'}{sep}policy",
        "--add-data", f"{ROOT / 'tools'}{sep}tools",
        "--add-data", f"{ctk_path}{sep}customtkinter",
        "--hidden-import", "yaml",
        "--hidden-import", "customtkinter",
        "--hidden-import", "tkinter",
        "--paths", str(ROOT),
        "--clean",
        "--noconfirm",
        str(ROOT / "ui" / "app.py"),
    ])

    icon = ROOT / "assets" / "icon.ico"
    if icon.exists():
        args.extend(["--icon", str(icon)])

    print("  Running PyInstaller...\n")
    result = subprocess.run(args, cwd=str(ROOT))

    if result.returncode != 0:
        print(f"\n  Build failed with code {result.returncode}\n")
        sys.exit(1)

    exe_path = ROOT / "dist" / f"{app_name}.exe"
    fallback_path = ROOT / "dist" / app_name
    built_path = exe_path if exe_path.exists() else fallback_path

    if built_path.exists():
        size_mb = built_path.stat().st_size / (1024 * 1024)
        print("\n  Build successful!")
        print(f"  Output: {built_path}")
        print(f"  Size: {size_mb:.1f} MB\n")
    else:
        print("\n  Build completed but artifact not found at expected paths.\n")


if __name__ == "__main__":
    build()
