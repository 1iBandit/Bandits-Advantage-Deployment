# app/app.py
# Thin entry point for Streamlit Cloud (recommended in DEPLOYMENT.md).
# Public deployment renders *only* Friend Mode (the calm companion experience).
# Analyst Workbench surfaces are available locally for personal analysis use only.
#
# SOT v0.2: Reads ONLY from data/sot/semantic/* (behavior_semantic drives gating).
# Raw SOT is blocked when FRIEND_OF_1IBANDIT_DEPLOYMENT=1.
# Run nightly_materializer after acquisition for fresh Excel/Power BI/Friend views.
import os
import sys
import runpy
from pathlib import Path

# Force pure Friend of 1iBandit mode in the public deployment.
os.environ["FRIEND_OF_1IBANDIT_DEPLOYMENT"] = "1"

root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root))

# Execute as __main__ so top-level Streamlit code (the entire surface) behaves as if run directly.
runpy.run_path(str(root / "analyst_workbench.py"), run_name="__main__")
