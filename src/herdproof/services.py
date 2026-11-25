"""Read model over the warehouse marts, shared by the API and the demo export. Lender reads check live consent."""

from typing import Any

import duckdb

from herdproof import consent
from herdproof.config import settings
from herdproof.levers import improvement_levers

Con = duckdb.DuckDBPyConnection


class NotFound(LookupError):
    pass


class ConsentRequired(PermissionError):
    pass


def _clean(v: Any) -> Any:
    if isinstance(v, float):
        return round(v, 3)
    if hasattr(v, "isoformat"):
        return v.isoformat()
    return v


def rows(con: Con, sql: str, params: list | None = None) -> list[dict]:
    cur = con.execute(sql, params or [])
    cols = [d[0] for d in cur.description]
    return [{c: _clean(v) for c, v in zip(cols, r, strict=True)} for r in cur.fetchall()]


def one(con: Con, sql: str, params: list | None = None) -> dict:
    found = rows(con, sql, params)
    if not found:
        raise NotFound(f"No record for {params}")
    return found[0]


def farm(con: Con, farm_id: str) -> dict:
    f = one(con, "select * from staging.stg_hp__farms where farm_id = ?", [farm_id])
    conn = rows(
        con,
        "select source, auth_type, connected_at from raw.hp_connections where farm_id = ? order by source",
        [farm_id],
    )
    return {**f, "connections": conn, "consents": consent.active(con, farm_id)}


def footprint(con: Con, farm_id: str) -> dict:
    fp = one(con, "select * from marts.fct_farm_footprint where farm_id = ?", [farm_id])
    flows = one(con, "select * from intermediate.int_herd_flows where farm_id = ?", [farm_id])
    classes = rows(
        con,
        """select gaf_class, quarter, round(head, 1) as head, round(liveweight_kg, 1) as liveweight_kg,
                                  round(liveweight_gain_kg_day, 3) as liveweight_gain_kg_day
                           from intermediate.int_herd_class_quarters where farm_id = ? order by gaf_class, quarter""",
        [farm_id],
    )
    # Give-to-get: only farms in the benchmark pool see the comparison.
    shared = consent.has_consent(con, farm_id, "regional_benchmark")
    bench = (
        rows(con, "select * exclude (farm_id) from marts.dim_farm_benchmark where farm_id = ?", [farm_id])
        if shared
        else []
    )
    return {
        "farm_id": farm_id,
        **{k: v for k, v in fp.items() if k != "farm_id"},
        "herd_flows": flows,
        "gaf_inputs": classes,
        "benchmark": bench[0] if bench else None,
    }


def levers(con: Con, farm_id: str) -> list[dict]:
    land = one(
        con,
        """select p.boundary_area_ha, f.zone from intermediate.int_pasture_capacity p
                       join staging.stg_hp__farms f using (farm_id) where farm_id = ?""",
        [farm_id],
    )
    return improvement_levers(footprint(con, farm_id), land["boundary_area_ha"], land["zone"])


def benchmarks(con: Con) -> list[dict]:
    return rows(con, "select * from marts.mart_regional_benchmark where is_published order by level, benchmark_key")


def reconciliation(con: Con, farm_id: str) -> dict:
    summary = one(con, "select * from marts.fct_reconciliation where farm_id = ?", [farm_id])
    checks = rows(
        con,
        "select * exclude (farm_id) from marts.fct_reconciliation_checks where farm_id = ? order by weight desc",
        [farm_id],
    )
    return {**summary, "checks": checks}


def deforestation(con: Con, farm_id: str) -> dict:
    d = one(con, "select * from marts.fct_deforestation where farm_id = ?", [farm_id])
    series = rows(
        con,
        "select obs_date, woody_area_ha from staging.stg_satellite__woody where farm_id = ? order by obs_date",
        [farm_id],
    )
    return {**d, "cutoff_date": "2020-12-31", "series": series}


def _borrower_view(row: dict, shared: bool) -> dict:
    """Lender-visible borrower row: farm-derived figures only when the borrower shares with this lender."""
    base = {
        k: row[k]
        for k in (
            "facility_id",
            "farm_id",
            "farm_name",
            "region_name",
            "state",
            "outstanding_aud",
            "attribution_factor",
            "baseline_score",
            "baseline_option",
            "baseline_financed_t",
        )
    }
    if shared and row["is_connected"]:
        return {
            **base,
            "status": "reconciled" if row["assurance_ready"] else "farm_reported",
            "assurance_ready": row["assurance_ready"],
            "shared": True,
            "current_score": row["connected_score"],
            "current_option": row["connected_option"],
            "current_financed_t": row["connected_financed_t"],
            "farm_emissions_t": row["connected_farm_t"],
            "intensity_kg_per_kg_lw": row["intensity_kg_per_kg_lw"],
            "confidence": row["confidence"],
            "n_fail": row["n_fail"],
            "n_warn": row["n_warn"],
            "deforestation_status": row["deforestation_status"],
        }
    return {
        **base,
        "status": "proxy",
        "shared": False,
        "current_score": row["baseline_score"],
        "current_option": row["baseline_option"],
        "current_financed_t": row["baseline_financed_t"],
    }


def lender_portfolio(con: Con, lender_id: str) -> dict:
    loans = rows(con, "select * from marts.fct_borrower_pcaf where lender_id = ? order by farm_name", [lender_id])
    if not loans:
        raise NotFound(f"lender {lender_id}")
    borrowers = [_borrower_view(r, consent.has_consent(con, r["farm_id"], f"lender_share:{lender_id}")) for r in loans]
    total = sum(b["outstanding_aud"] for b in borrowers)

    def weighted(key: str) -> float:
        return round(sum(b[key] * b["outstanding_aud"] for b in borrowers) / total, 2)

    for b in borrowers:  # score once assurance-ready packs are independently assured (PCAF 1a)
        b["assured_score"] = 1 if b.get("assurance_ready") else b["current_score"]

    return {
        "lender_id": lender_id,
        "lender_name": loans[0]["lender_name"],
        "segment": loans[0]["lender_segment"],
        "summary": {
            "borrowers": len(borrowers),
            "outstanding_aud": total,
            "baseline_financed_t": round(sum(b["baseline_financed_t"] for b in borrowers), 1),
            "current_financed_t": round(sum(b["current_financed_t"] for b in borrowers), 1),
            "baseline_pcaf_score": weighted("baseline_score"),
            "current_pcaf_score": weighted("current_score"),
            "assured_pcaf_score": weighted("assured_score"),
            # Reported vs estimated split of exposure, as climate disclosure guidance asks lenders to show.
            "reported_exposure_pct": round(100 * sum(b["outstanding_aud"] for b in borrowers if b["shared"]) / total, 1),
            "reconciled": sum(b["status"] == "reconciled" for b in borrowers),
            "farm_reported": sum(b["status"] == "farm_reported" for b in borrowers),
            "proxy": sum(b["status"] == "proxy" for b in borrowers),
            "flags": sum(1 for b in borrowers if b.get("n_fail")),
            "deforestation_review": sum(b.get("deforestation_status") == "review" for b in borrowers),
        },
        "borrowers": borrowers,
    }


def borrower_detail(con: Con, lender_id: str, farm_id: str) -> dict:
    if not consent.has_consent(con, farm_id, f"lender_share:{lender_id}"):
        raise ConsentRequired(f"{farm_id} has not consented to share with {lender_id}")
    loan = one(con, "select * from marts.fct_borrower_pcaf where lender_id = ? and farm_id = ?", [lender_id, farm_id])
    return {
        "loan": loan,
        "footprint": footprint(con, farm_id),
        "reconciliation": reconciliation(con, farm_id),
        "deforestation": deforestation(con, farm_id),
    }


def processor_cohort(con: Con, processor_id: str) -> dict:
    p = one(con, "select * from staging.stg_hp__processors where processor_id = ?", [processor_id])
    segs = rows(
        con,
        "select * exclude (processor_id) from marts.mart_processor_cohort where processor_id = ? "
        "order by segment = 'All suppliers' desc, segment",
        [processor_id],
    )
    return {**p, "k_min": 5, "segments": segs}


def period() -> dict:
    return {"start": settings.period_start.isoformat(), "end": settings.period_end.isoformat(), "label": "FY2025-26"}
