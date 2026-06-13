# app/app.py
# Thin entry point for Streamlit Cloud (recommended in DEPLOYMENT.md).
# Robust runner for the canonical Decision Surface (Hero Decision Band first + Analyst/Friend modes).
import sys
import runpy
from pathlib import Path

root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root))

# Execute as __main__ so top-level Streamlit code (the entire surface) behaves as if run directly.
runpy.run_path(str(root / "analyst_workbench.py"), run_name="__main__")
