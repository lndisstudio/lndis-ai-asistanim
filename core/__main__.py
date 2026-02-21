"""
Allow running via:
  python -m core          -> CLI (terminal)
  python -m core --ui     -> Desktop GUI
"""

import sys

if __name__ == "__main__":
    if "--ui" in sys.argv:
        from ui.app import main
        main()
    else:
        from core.cli import main
        main()
