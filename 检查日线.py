"""Compatibility entry point; implementation lives in 程序/检查资料.py."""
import runpy
from pathlib import Path
if __name__ == "__main__":
    runpy.run_path(str(Path(__file__).resolve().parent / "程序" / "检查资料.py"), run_name="__main__")
