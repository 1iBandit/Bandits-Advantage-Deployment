"""
Portfolio Layer Manual Seeding / Input Mechanism (Phase 1 – Chunk C)

Minimal, explicit mechanism to define and seed the initial 25 portfolios
from structured CSV files.

Primary formats:
- portfolios.csv : portfolio_id, portfolio_name, portfolio_type
- holdings.csv   : portfolio_id, ticker, acquisition_date, acquisition_price,
                   shares_initial, tax_basis, bucket_id (optional)

All seeded snapshots are created with Phase 1 guardrails:
- intelligence_layers_enabled = False
- mutation_rules = {"apply_actions": False} (read-only)
- data_completeness = "manual_seed"

No intelligence, no auto-generation, no mutation.
"""

import csv
from datetime import date
from pathlib import Path
from typing import List, Dict, Set, Optional

from ..models.portfolio import (
    HoldingSnapshot,
    PortfolioStateSnapshot,
)
from .persistence import save_snapshot


# Locked 12 portfolio types from Phase 0 Chunk 1
VALID_PORTFOLIO_TYPES: Set[str] = {
    "New Investor / Starter",
    "Capital Preservation",
    "Growth",
    "Aggressive Growth",
    "Income / Monthly Distribution",
    "Balanced / Moderate",
    "Tactical / Opportunistic",
    "Dividend Focus",
    "Recovery / Turnaround",
    "Inflation Hedge",
    "Retirement Income",
    "High Conviction / Satellite",
}


def _parse_date(value: str) -> date:
    """Parse YYYY-MM-DD date string."""
    return date.fromisoformat(value.strip())


def load_portfolio_definitions(
    portfolios_csv: str,
    holdings_csv: str
) -> List[PortfolioStateSnapshot]:
    """
    Load portfolio definitions from two CSV files and return
    ready-to-persist PortfolioStateSnapshot objects.

    portfolios_csv columns (required):
        portfolio_id, portfolio_name, portfolio_type

    holdings_csv columns (required):
        portfolio_id, ticker, acquisition_date, acquisition_price,
        shares_initial, tax_basis

    holdings_csv columns (optional):
        bucket_id

    Raises ValueError for invalid portfolio_type or missing data.
    """
    # Load portfolios
    portfolios: Dict[str, Dict] = {}
    with open(portfolios_csv, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            pid = row["portfolio_id"].strip()
            ptype = row["portfolio_type"].strip()
            if ptype not in VALID_PORTFOLIO_TYPES:
                raise ValueError(
                    f"Invalid portfolio_type '{ptype}' for portfolio_id '{pid}'. "
                    f"Must be one of the 12 locked types."
                )
            portfolios[pid] = {
                "portfolio_id": pid,
                "portfolio_name": row["portfolio_name"].strip(),
                "portfolio_type": ptype,
            }

    # Load holdings grouped by portfolio_id
    holdings_by_pid: Dict[str, List[Dict]] = {}
    with open(holdings_csv, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            pid = row["portfolio_id"].strip()
            if pid not in portfolios:
                continue

            shares_init = float(row["shares_initial"])
            acq_price = float(row["acquisition_price"])
            init_value = shares_init * acq_price

            holding = {
                "ticker": row["ticker"].strip(),
                "acquisition_date": _parse_date(row["acquisition_date"]),
                "acquisition_price": acq_price,
                "shares_initial": shares_init,
                "initial_investment_value": init_value,
                "initial_weight_pct": 0.0,
                "tax_basis": float(row["tax_basis"]),
                "bucket_id": row.get("bucket_id", "").strip() or None,
                # At seed time for Phase 1, current state mirrors initial
                "shares_current": shares_init,
                "current_price": acq_price,
                "current_value": init_value,
                "pnl_abs": 0.0,
                "pnl_pct": 0.0,
                "current_weight_pct": 0.0,
            }
            holdings_by_pid.setdefault(pid, []).append(holding)

    # Build snapshots
    snapshots: List[PortfolioStateSnapshot] = []
    for pid, pinfo in portfolios.items():
        raw_holdings = holdings_by_pid.get(pid, [])
        holdings = [HoldingSnapshot(**h) for h in raw_holdings]

        total_init_value = sum(h.initial_investment_value for h in holdings) or 1.0
        for h in holdings:
            h.initial_weight_pct = round((h.initial_investment_value / total_init_value) * 100, 2)

        snap = PortfolioStateSnapshot(
            portfolio_id=pinfo["portfolio_id"],
            portfolio_name=pinfo["portfolio_name"],
            portfolio_type=pinfo["portfolio_type"],
            as_of_date=date.today(),
            source="manual_seed",
            total_value=total_init_value,
            total_pnl_abs=0.0,
            total_pnl_pct=0.0,
            intelligence_layers_enabled=False,
            mutation_rules={"apply_actions": False},
            data_completeness="manual_seed",
            holdings=holdings,
            logic_trace=[],
            action_rationale=None,
            unified_portfolio_view_rationale=None,
            escalation_notifications=[],
        )
        snapshots.append(snap)

    return snapshots


def seed_from_csv(
    portfolios_csv: str,
    holdings_csv: str,
    base_path: str
) -> List[str]:
    """
    Load definitions from CSV and immediately persist them via the
    JSONL persistence layer (Chunk B).

    Returns list of file paths written.
    """
    snapshots = load_portfolio_definitions(portfolios_csv, holdings_csv)
    saved_paths: List[str] = []
    for snap in snapshots:
        path = save_snapshot(snap, base_path)
        saved_paths.append(path)
    return saved_paths


def create_example_capital_preservation_seed(
    base_path: str,
    portfolios_csv: Optional[str] = None,
    holdings_csv: Optional[str] = None,
) -> List[str]:
    """
    Convenience helper that writes example CSVs for a "Capital Preservation"
    portfolio with 6 holdings and then seeds them.

    Returns the list of saved snapshot file paths.
    """
    import tempfile

    if portfolios_csv is None or holdings_csv is None:
        tmp = Path(tempfile.mkdtemp())
        portfolios_csv = str(tmp / "portfolios.csv")
        holdings_csv = str(tmp / "holdings.csv")

    # Write example portfolios.csv
    with open(portfolios_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["portfolio_id", "portfolio_name", "portfolio_type"])
        writer.writerow([
            "preservation_example_01",
            "Example Capital Preservation",
            "Capital Preservation"
        ])

    # Write example holdings.csv (6 holdings)
    holdings_data = [
        ["preservation_example_01", "BND", "2024-01-15", "72.50", "200", "14500", "core"],
        ["preservation_example_01", "TLT", "2024-02-01", "95.20", "150", "14280", "core"],
        ["preservation_example_01", "GLD", "2024-03-10", "185.00", "80", "14800", "inflation"],
        ["preservation_example_01", "JNJ", "2024-01-20", "158.30", "60", "9498", "core"],
        ["preservation_example_01", "KO", "2024-02-15", "59.80", "120", "7176", "core"],
        ["preservation_example_01", "VYM", "2024-03-05", "108.40", "90", "9756", "income"],
    ]
    with open(holdings_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "portfolio_id", "ticker", "acquisition_date", "acquisition_price",
            "shares_initial", "tax_basis", "bucket_id"
        ])
        for row in holdings_data:
            writer.writerow(row)

    return seed_from_csv(portfolios_csv, holdings_csv, base_path)
