# Phase 4L — Clean Deployment Tree Specification v0.1

**Status:** Draft — ready for review and lock  
**Date:** 2026-06  
**Owner:** David (with Grok Build)  
**Dependencies:** Phase 4L locked contract, existing `analyst_workbench.py`, `src/engine/portfolio/narrative.py`, and `test_phase4l_decision_surface.py`

---

## 1. Goal

Define a minimal, canonical deployment tree that:

- Deploys reliably to Streamlit Cloud with zero import or data conflicts.
- Uses the existing engine + narrative + Decision Surface code without duplication.
- Maintains the .grok worktree as the **single source of truth** (canonical tree).
- Eliminates raw data, logs, tests, legacy trees, and research artifacts from the deployed surface.
- Provides one clear entry point and one clear module root.
- Guarantees local `streamlit run` behavior is identical to Cloud behavior.

The deployment tree is a **projection**, not a fork.

---

## 2. Hard Constraints (Non-Negotiable)

- No logic duplication between canonical worktree and deployment tree.
- All synthesis logic remains exclusively in `src/engine/portfolio/narrative.py`.
- The deployment tree is read-only from an editing perspective. Never make logic changes directly in the deployment repo.
- Local run parity must be maintained (Hero Decision Band, mode switching, abstention treatment, quiet state, and `friend_language_version` must behave identically).
- The 4L Ritual Validation Script (`test_phase4l_decision_surface.py`) **must pass** in the deployment tree before any sync.

---

## 3. Recommended Deployment Tree Layout

When connected to Streamlit Cloud, the following structure is used:

```
.
├── app/
│   └── app.py                    # Thin Streamlit entry point (imports and runs analyst_workbench)
├── src/
│   └── engine/
│       ├── __init__.py
│       ├── data/
│       ├── io/
│       ├── models/
│       ├── pipeline/
│       ├── portfolio/
│       │   ├── __init__.py
│       │   ├── narrative.py      # Contains all 4L + 4K presenters (Hero Band, Friend Mode, etc.)
│       │   ├── workbench_ui.py
│       │   └── ...
│       └── utils/
├── config/
│   └── universe/
│       └── core_tickers.csv      # Minimal required universe only
├── analyst_workbench.py          # Main application logic (4L/4K/4I/4J aware)
├── requirements.txt
├── README.md
├── DEPLOYMENT.md                 # This spec + operational notes
└── .streamlit/
    └── config.toml               # (optional but recommended for layout / theme)
```

**Rationale:**
- `app/app.py` is the thinnest possible entry point (Streamlit Cloud strongly prefers this pattern).
- `src/` remains the single module root.
- `analyst_workbench.py` stays at the root of the deployment tree for simplicity (imported by `app/app.py`).
- Only the minimal files required to render the Decision Surface are present.

---

## 4. Inclusion Rules (What Ships)

- `analyst_workbench.py` (current 4L-aware version with Hero Decision Band + mode switching)
- `src/engine/portfolio/` (full subtree — **all synthesis logic lives here**)
- Supporting `src/engine/` modules required by the workbench:
  - `models/`
  - `pipeline/`
  - `utils/`
  - `io/`
  - `data/`
- `config/universe/core_tickers.csv` (minimal universe)
- Note: Acquisition manifests are written to `data/acquisition_manifests/` (canonical only — never shipped to deployment tree).
- `requirements.txt` (curated, minimal set — see section below)
- `README.md` (deployment-focused)
- `DEPLOYMENT.md` (this document)
- `.streamlit/config.toml` (if layout or theme settings are used)

---

## 5. Exclusion Rules (What Never Ships)

- `BanditsAdvantageEngine/` (legacy tree)
- `Config_Private/`
- `data/raw/` (full price history CSVs)
- `Logs/`
- `Output/`
- `scripts/` (diagnostics, ad-hoc runners, generators)
- `Docs/` (all contracts, roadmap, Phase documents — these live **only** in the canonical tree)
- All `test_*.py` files and the `tests/` directory
- `.grok/`, `.vscode/`, `.idea/`, `__pycache__/`, `*.pyc`, `*.log`, etc.
- Any large historical artifacts, replay CSVs, or ad-hoc outputs

**Core Principle:** The deployment tree contains **only** what is required to:
1. Load a portfolio
2. Run the engine
3. Build the narrative spine (4A–4J)
4. Render the Decision Surface (4L + 4K child + 4I/4J)

---

## 6. Synchronization Strategy (Critical)

**Canonical source of truth:** Your `.grok` worktree (`finalizing-bandits-advantage`)

**Deployment target:** Separate GitHub repository (the one connected to Streamlit Cloud)

**Rules:**
- All changes originate in the canonical worktree.
- Changes **must** pass `test_phase4l_decision_surface.py` (and any future 4L rituals) before syncing.
- The deployment tree is **read-only** for editing. Never make logic changes directly in the deployment repo.
- Sync is performed via a deliberate, documented ritual.

### Recommended Sync Ritual (Enforced by Helper Script)

1. In the **canonical** worktree, run the current stack health ritual:
   - `python test_phase5_stack_health.py` → must report **PASSED** (this is the single source of truth gate for the entire Phase 5 data layer + 4L Decision Surface).

2. Run the sync helper (it will re-verify the ritual, show a preview, copy only allowed files, and print the commit template):
   ```powershell
   .\scripts\sync-to-deployment.ps1
   ```

3. In the deployment repo:
   - Review the changes.
   - Commit using the template printed by the script (it includes the canonical commit hash).
   - Push.

The script `scripts/sync-to-deployment.ps1` (now present in the canonical tree) makes the process repeatable and hard to get wrong. It automatically runs/checks the ritual and only proceeds on PASSED.

See the script itself for -SkipRitual / -Force / -Target options and full comments.

---

## 7. Streamlit Cloud Configuration

- **Entry point:** `app/app.py` (recommended) or `analyst_workbench.py` at the root.
- **Module root:** `src/` must be on `PYTHONPATH`. Streamlit Cloud automatically adds the project root, so `from src.engine.portfolio...` works when the structure above is followed.
- **Secrets:** None required for current scope (no private config is shipped).
- **requirements.txt:** Must be minimal and pinned where practical.

### Example `app/app.py` (thin wrapper)

```python
# app/app.py
"""
Thin entry point for Streamlit Cloud.
Imports the Decision Surface from the canonical analyst_workbench.py.
"""

import sys
from pathlib import Path

# Ensure src/ is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Run the real application
import analyst_workbench  # This will execute the Streamlit app when run via streamlit run

if __name__ == "__main__":
    # Streamlit Cloud runs the module; the import above triggers main()
    pass
```

---

## 8. Local Run Parity

To run the deployment tree locally (must behave identically to Cloud):

```powershell
# From the deployment repository root
pip install -r requirements.txt
streamlit run app/app.py
# or
streamlit run analyst_workbench.py
```

Both must produce:
- The Hero Decision Band as the dominant, always-visible element
- Working Analyst ↔ Friend mode switching
- Correct abstention treatment (visually primary)
- Quiet state handling
- `friend_language_version = "v0.1"` in Friend Notes

The 4L Ritual Validation Script must also pass:
```powershell
python test_phase4l_decision_surface.py
```

---

## 9. Requirements.txt (Curated for Deployment)

Only what the Decision Surface actually needs at runtime:

```txt
pandas>=2.0
numpy>=1.24
openpyxl>=3.1
pyarrow>=14.0          # Preferred for any history; falls back gracefully
python-dotenv>=1.0
streamlit>=1.35        # Explicitly declared for Cloud
```

**Do not include** `pytest` or other dev/test dependencies in the deployment `requirements.txt`.

---

## 10. Risks & Mitigations

| Risk                              | Mitigation |
|-----------------------------------|----------|
| Sync drift between canonical and deployment | Strict “canonical-first” rule + ritual validation gate before every sync |
| Import path differences (local vs Cloud) | Enforce identical structure + PYTHONPATH handling in `app/app.py` |
| Future 4L changes accidentally missed in deployment | Ritual script is part of the pre-sync checklist |
| Scope creep (someone tries to ship tests/docs) | `DEPLOYMENT.md` explicitly defines exclusion rules |
| Accidental edits in the deployment repo | Treat the deployment repo as generated/read-only; document in README |

---

## 11. How to Use This Document

1. Read this file in the **canonical** worktree.
2. Make all logic and presenter changes in the canonical tree.
3. Run `test_phase4l_decision_surface.py` — it **must** pass.
4. Perform the sync ritual above.
5. Deploy / push the deployment repo to Streamlit Cloud.

Any change that would require updating this document (new files that must ship, new exclusion rules, new sync steps) should be proposed as an update to this `DEPLOYMENT.md` in the canonical tree first.

---

## 12. Troubleshooting

**"ModuleNotFoundError: No module named 'src.engine...'"**
- Ensure you are running from the deployment root.
- Confirm `src/` directory exists at the root of the deployment repo.
- For local testing: `PYTHONPATH=. streamlit run app/app.py`

**Hero Decision Band or Friend Mode looks different in Cloud vs local**
- You are likely running different versions of `analyst_workbench.py` or `narrative.py`.
- Re-sync from canonical and re-run the 4L ritual.

**Missing `core_tickers.csv`**
- The deployment tree only ships `config/universe/core_tickers.csv`. Do not reference any files under `data/raw/`.

**Streamlit Cloud build fails on requirements**
- Use the curated `requirements.txt` shown above. Remove `pytest` and any other dev-only packages.

---

**This document is the contract for the Phase 4L deployment surface.**  
It lives only in the canonical `.grok` worktree. The deployment repository is a faithful, minimal projection of it.

When this spec is locked, future 4L work (further Hero Band refinements, Friend Mode enhancements, visual hierarchy improvements) must respect the inclusion/exclusion rules and the canonical-first sync discipline.

---

*Preserved principle from Phase 4L contract: All synthesis logic remains in `narrative.py`. The Decision Surface is presentation only. The deployment tree exists to make that surface reliably available to humans.*