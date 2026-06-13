# app/app.py
# Thin entry point for Streamlit Cloud (recommended in DEPLOYMENT.md).
# Imports the full Decision Surface (dominant Hero Band + Analyst/Friend modes).

import sys
from pathlib import Path

root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root))

import analyst_workbench

if __name__ == "__main__":
    pass
