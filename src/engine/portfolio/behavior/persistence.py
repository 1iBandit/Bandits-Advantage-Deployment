"""
Persistence Layer v0.3 (Localized File-Based Storage for 1i_Bandit Sandbox)

Lightweight, encrypted (Fernet), integrity-protected local storage for the
canonical 1i_Bandit testing Buddy. Survives browser refreshes and app restarts.

Design:
- Application-derived symmetric key (lightweight for v0.3; stronger user-controlled
  encryption planned later).
- JSON manifest inside encrypted file.
- Automatic fallback to the pristine December 2025 baseline on missing/corrupt file.
- Always resets behavioral_state and behavior_event_log to fresh on load (even from disk).
- Persists: sandbox_ledger, unfiltered_view, and relevant registry snapshot.

Cross-platform paths:
- Windows: %APPDATA%\\BanditOS\\1i_Bandit_state.enc
- macOS/Linux: ~/.banditos/1i_Bandit_state.enc

The directory is created automatically.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

from cryptography.fernet import Fernet, InvalidToken

# =============================================================================
# Application-derived key (lightweight for v0.3 demo)
# In a real deployment this should come from a secure source / user secret.
# For now we use a fixed key so the sandbox state is portable across runs.
# Fernet key must be 32 urlsafe base64 bytes.
# =============================================================================
# Generated once for this demo. Replace in production with proper key mgmt.
_FERNET_KEY = b'kL3vK8vN5pQ7rS9tU2vW4xY6zA8bC0dE2fG4hI6jK8lM='  # 32-byte base64 example
_FERNET = Fernet(_FERNET_KEY)


def _get_state_dir() -> Path:
    """Return (and create) the cross-platform directory for Buddy state files."""
    if os.name == "nt":
        base = Path(os.getenv("APPDATA", str(Path.home()))) / "BanditOS"
    else:
        base = Path.home() / ".banditos"
    base.mkdir(parents=True, exist_ok=True)
    return base


def _get_state_file_path(buddy_id: str) -> Path:
    """Return the full path to the encrypted state file for a given Buddy."""
    return _get_state_dir() / f"{buddy_id}_state.enc"


def _ensure_directory_exists() -> None:
    """Ensure the state directory exists (idempotent)."""
    _get_state_dir()


def _encrypt_manifest(manifest: Dict[str, Any]) -> bytes:
    """Encrypt a JSON-serializable manifest."""
    plaintext = json.dumps(manifest, default=str).encode("utf-8")
    return _FERNET.encrypt(plaintext)


def _decrypt_manifest(encrypted: bytes) -> Optional[Dict[str, Any]]:
    """Decrypt and parse a manifest. Returns None on any failure."""
    try:
        plaintext = _FERNET.decrypt(encrypted)
        return json.loads(plaintext)
    except (InvalidToken, json.JSONDecodeError, TypeError):
        return None


# =============================================================================
# Public API
# =============================================================================

def load_buddy_state_from_disk(buddy_id: str) -> Optional[Dict[str, Any]]:
    """
    Load the persisted state for a Buddy.

    Returns the manifest dict or None if the file does not exist or is invalid.
    """
    _ensure_directory_exists()
    path = _get_state_file_path(buddy_id)
    if not path.exists():
        return None

    try:
        encrypted = path.read_bytes()
        manifest = _decrypt_manifest(encrypted)
        if not isinstance(manifest, dict):
            return None
        return manifest
    except Exception:
        # Any read/decrypt error -> treat as invalid (will trigger baseline seed)
        return None


def save_buddy_state_to_disk(buddy_id: str, manifest: Dict[str, Any]) -> bool:
    """
    Persist the given manifest for a Buddy.

    Returns True on success, False on failure (non-fatal for the session).
    """
    _ensure_directory_exists()
    path = _get_state_file_path(buddy_id)
    try:
        encrypted = _encrypt_manifest(manifest)
        path.write_bytes(encrypted)
        return True
    except Exception:
        # Non-fatal: the session continues with in-memory state
        return False


def initialize_or_load_buddy_session(buddy_id: str = "1i_Bandit") -> None:
    """
    State Ingestion Validation Loop for the 1i_Bandit sandbox.

    - Tries to load existing encrypted state from disk.
    - On success: restores sandbox_ledger, unfiltered_view, and relevant registry snapshot.
    - On any failure (missing, corrupt, decrypt error): seeds the pristine
      December 2025 canonical baseline and immediately persists it.
    - Always resets behavioral_state and behavior_event_log to a fresh start
      (even when restoring from disk). This keeps the behavioral engine stateless
      across restarts while the ledger itself survives.

    Must be called early in the Friend Mode path for the sandbox context.
    """
    # Always start behavioral context fresh (per spec)
    if "buddy_id" not in st.session_state:
        st.session_state["buddy_id"] = buddy_id

    st.session_state["behavioral_state"] = "NEUTRAL"
    st.session_state["behavior_event_log"] = []

    manifest = load_buddy_state_from_disk(buddy_id)

    if manifest is None:
        # Seed the canonical December 2025 baseline exactly as defined
        baseline_ledger = {
            "TSNF":  {"shares": 760,  "price": 42.50, "date": "2025-11"},
            "IFRA":  {"shares": 211,  "price": 38.20, "date": "2025-08"},
            "VALE":  {"shares": 1100, "price": 12.10, "date": "2025-05"},
            "PL":    {"shares": 250,  "price": 18.45, "date": "2025-10"},
            "NEE":   {"shares": 150,  "price": 72.30, "date": "2025-09"},
            "DOCN":  {"shares": 125,  "price": 34.00, "date": "2025-06"},
            "PBR.A": {"shares": 400,  "price": 14.80, "date": "2025-07"},
            "IGF":   {"shares": 350,  "price": 45.15, "date": "2025-04"},
            "PLUG":  {"shares": 140,  "price": 3.20,  "date": "2025-12"},
        }
        st.session_state["sandbox_ledger"] = baseline_ledger
        st.session_state["unfiltered_view"] = False

        # Seed a minimal relevant registry snapshot for the sandbox (isolated)
        st.session_state["portfolio_behavioral_registry"] = st.session_state.get(
            "portfolio_behavioral_registry", {}
        )
        # Ensure the sandbox has its own entry if the router hasn't created it yet
        if buddy_id not in st.session_state["portfolio_behavioral_registry"]:
            st.session_state["portfolio_behavioral_registry"][buddy_id] = {
                "name": "1i_Bandit Sandbox",
                "state": "NEUTRAL",
                "events": [],
                "tier": 1,
                "max_dd": "15%",
                "horizon": "12-Month Strategic Marathon",
                "profile": {
                    "profile_id": f"{buddy_id}_friend",
                    "personality_type": "BalancedCore",
                    "primary_goals": ["long_term_capital_growth"],
                    "risk_constraints": {"max_drawdown_pct": 15.0},
                    "sector_caps": {},
                    "ticker_caps": {},
                    "behavioral_tendencies": [],
                    "communication_preference": "balanced",
                    "free_text_notes": "Canonical 1i_Bandit testing profile",
                    "created_at": "2025-12-01",
                    "provenance": {"source": "baseline_seed_v0.3"},
                },
            }

        # Immediately persist the fresh baseline so it survives the first refresh
        manifest = {
            "ledger": baseline_ledger,
            "unfiltered_view": False,
            "registry": st.session_state["portfolio_behavioral_registry"].get(buddy_id, {}),
        }
        save_buddy_state_to_disk(buddy_id, manifest)
    else:
        # Valid persisted state found – restore what we care about for the sandbox
        st.session_state["sandbox_ledger"] = manifest.get("ledger", {})
        st.session_state["unfiltered_view"] = manifest.get("unfiltered_view", False)

        # Merge relevant registry snapshot if present (non-destructive)
        if "registry" in manifest and buddy_id in st.session_state.get("portfolio_behavioral_registry", {}):
            # Only restore the sandbox-specific slice to avoid clobbering other slots
            st.session_state["portfolio_behavioral_registry"][buddy_id].update(
                manifest["registry"]
            )


def trigger_encrypted_disk_sync(buddy_id: str = "1i_Bandit") -> bool:
    """
    Persist the current sandbox-relevant state to disk.

    Called after meaningful user actions (manual ledger updates, etc.).
    Returns True on successful write, False on failure (non-fatal).
    """
    if "sandbox_ledger" not in st.session_state:
        return False

    manifest = {
        "ledger": st.session_state["sandbox_ledger"],
        "unfiltered_view": st.session_state.get("unfiltered_view", False),
    }

    # Include the sandbox slice of the registry if it exists
    reg = st.session_state.get("portfolio_behavioral_registry", {})
    if buddy_id in reg:
        manifest["registry"] = reg[buddy_id]

    return save_buddy_state_to_disk(buddy_id, manifest)