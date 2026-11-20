"""Exports backend outputs into the single self-contained demo page (data embedded, no network)."""

import json
from datetime import UTC, datetime, time

import duckdb

from herdproof import consent, evidence, services
from herdproof.config import settings
from herdproof.synth import HERO_FARM

PLACEHOLDER = "/*__HERDPROOF_DATA__*/null"
HERO_LENDER = "L1"
SHARE_SCOPES = ["footprint", "reconciliation", "deforestation"]


def _lender(con: duckdb.DuckDBPyConnection, lender_id: str) -> dict:
    portfolio = services.lender_portfolio(con, lender_id)
    packs = {
        b["farm_id"]: evidence.lender_pack(con, lender_id, b["farm_id"]) for b in portfolio["borrowers"] if b["shared"]
    }
    return {**portfolio, "packs": packs}


def _hero(con: duckdb.DuckDBPyConnection) -> dict:
    hero = {
        "farm": services.farm(con, HERO_FARM),
        "footprint": services.footprint(con, HERO_FARM),
        "levers": services.levers(con, HERO_FARM),
        "reconciliation": services.reconciliation(con, HERO_FARM),
        "deforestation": services.deforestation(con, HERO_FARM),
        "report": evidence.grazier_report(con, HERO_FARM),
    }
    # The scripted demo lets the grazier grant lender sharing live; precompute that state, then roll it back.
    con.begin()
    at = datetime.combine(settings.as_at, time(9, 0), tzinfo=UTC)
    consent.grant(con, HERO_FARM, f"lender_share:{HERO_LENDER}", SHARE_SCOPES, at=at)
    after = services.lender_portfolio(con, HERO_LENDER)
    hero["on_share"] = {
        "lender_id": HERO_LENDER,
        "summary": after["summary"],
        "borrower": next(b for b in after["borrowers"] if b["farm_id"] == HERO_FARM),
        "pack": evidence.lender_pack(con, HERO_LENDER, HERO_FARM),
    }
    con.rollback()
    return hero


def payload(con: duckdb.DuckDBPyConnection) -> dict:
    return {
        "meta": {
            "as_at": settings.as_at.isoformat(),
            "period": services.period(),
            "hero_farm_id": HERO_FARM,
            "hero_lender_id": HERO_LENDER,
            "seed": settings.seed,
            "generated_at": settings.as_at.isoformat(),
        },
        "factors": services.rows(con, "select * from ref.ref_emission_factors"),
        "proxies": services.rows(con, "select * from ref.ref_pcaf_proxies"),
        "benchmarks": services.benchmarks(con),
        "benchmark_coverage": services.rows(
            con,
            "select level, benchmark_key, benchmark_name, n_farms, is_published "
            "from marts.mart_regional_benchmark order by level, benchmark_key",
        ),
        "hero": _hero(con),
        "lenders": [
            _lender(con, lid) for (lid,) in con.execute("select lender_id from raw.hp_lenders order by 1").fetchall()
        ],
        "processors": [
            services.processor_cohort(con, pid)
            for (pid,) in con.execute("select processor_id from raw.hp_processors order by 1").fetchall()
        ],
    }


def run() -> dict:
    with duckdb.connect(str(settings.db_path)) as con:
        data = payload(con)
    blob = json.dumps(data, separators=(",", ":"), ensure_ascii=False).replace("</", "<\\/")
    html = settings.template_path.read_text(encoding="utf-8")
    if PLACEHOLDER not in html:
        raise ValueError("Template is missing the data placeholder")
    settings.demo_out.parent.mkdir(parents=True, exist_ok=True)
    settings.demo_out.write_text(html.replace(PLACEHOLDER, blob), encoding="utf-8")
    return {"path": str(settings.demo_out), "bytes": settings.demo_out.stat().st_size}
