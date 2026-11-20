"""Paths and runtime settings, overridable via HERDPROOF_* environment variables."""

import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path

ROOT = Path(os.getenv("HERDPROOF_ROOT", Path(__file__).resolve().parents[2]))


@dataclass(frozen=True)
class Settings:
    root: Path = ROOT
    data_dir: Path = ROOT / "data"
    fixtures_dir: Path = ROOT / "data" / "fixtures"
    landing_dir: Path = ROOT / "data" / "landing"
    packs_dir: Path = ROOT / "data" / "packs"
    warehouse_dir: Path = ROOT / "warehouse"
    db_path: Path = Path(os.getenv("HERDPROOF_DUCKDB", ROOT / "data" / "herdproof.duckdb"))
    template_path: Path = Path(__file__).parent / "web" / "index.html"
    demo_out: Path = ROOT / "demo" / "index.html"
    seed: int = int(os.getenv("HERDPROOF_SEED", "20261120"))
    # Reporting period (Australian FY2026) and the fixed "as at" date keep demo hashes reproducible.
    period_start: date = date(2025, 7, 1)
    period_end: date = date(2026, 6, 30)
    as_at: date = date.fromisoformat(os.getenv("HERDPROOF_AS_AT", "2026-11-20"))
    llm_model: str = os.getenv("HERDPROOF_LLM_MODEL", "claude-sonnet-5-5")


settings = Settings()
