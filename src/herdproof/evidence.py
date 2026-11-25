"""Evidence packs: assembled from marts, narrated, then sealed with a SHA-256 content hash anyone can re-verify."""

import hashlib
import json
from typing import Any

from herdproof import consent, narrative, services
from herdproof.config import settings
from herdproof.services import Con

SCHEMA = "herdproof.evidence-pack/v0.1"
SOURCE_TABLES = {
    "agriwebb": ("agriwebb_animals", "agriwebb_records", "agriwebb_fields"),
    "nlis": ("nlis_movements",),
    "satellite": ("satellite_boundary", "satellite_pasture", "satellite_woody"),
}
REGISTRY_DDL = """create table if not exists app.evidence_packs (
    pack_id varchar primary key, farm_id varchar, pack_type varchar, lender_id varchar,
    content_hash varchar, issued_at date, body json)"""


def _normalise(v: Any) -> Any:
    if isinstance(v, float):
        r = round(v, 4)
        return int(r) if r.is_integer() else r
    if isinstance(v, dict):
        return {k: _normalise(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_normalise(x) for x in v]
    return v


def canonical(obj: Any) -> str:
    """Sorted keys, no whitespace, UTF-8; floats rounded to 4 dp and integral floats written as ints."""
    return json.dumps(_normalise(obj), sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def content_hash(pack: dict) -> str:
    body = {k: v for k, v in pack.items() if k != "integrity"}
    return hashlib.sha256(canonical(body).encode("utf-8")).hexdigest()


def seal(pack: dict) -> dict:
    pack = _normalise(pack)
    digest = content_hash(pack)
    pack_id = "HP-" + "-".join(digest[i : i + 4].upper() for i in range(0, 12, 4))
    return {
        **pack,
        "integrity": {
            "algorithm": "sha256",
            "content_hash": digest,
            "pack_id": pack_id,
            "canonicalisation": "JSON, sorted keys, no whitespace, UTF-8, floats to 4 dp, integrity block excluded",
        },
    }


def verify(pack: dict, con: Con | None = None) -> dict:
    claimed = (pack.get("integrity") or {}).get("content_hash")
    actual = content_hash(pack)
    result = {
        "valid": claimed == actual,
        "pack_id": (pack.get("integrity") or {}).get("pack_id"),
        "claimed_hash": claimed,
        "computed_hash": actual,
    }
    if con is not None and result["valid"]:
        con.execute(REGISTRY_DDL)
        row = con.execute(
            "select farm_id, lender_id from app.evidence_packs where pack_id = ?", [result["pack_id"]]
        ).fetchone()
        result["registered"] = row is not None
        if row and row[1]:
            result["consent_active"] = consent.has_consent(con, row[0], f"lender_share:{row[1]}")
    return result


def _snapshots(con: Con, farm: dict) -> list[dict]:
    """Hash the exact raw rows each source contributed, so the pack is tied to its inputs."""
    out = []
    for c in farm["connections"]:
        h, n = hashlib.sha256(), 0
        for table in SOURCE_TABLES[c["source"]]:
            for row in con.execute(
                f"select * from raw.{table} where farm_id = ? order by all", [farm["farm_id"]]
            ).fetchall():
                h.update(canonical([str(x) for x in row]).encode())
                n += 1
        out.append(
            {
                "source": c["source"],
                "auth": c["auth_type"],
                "connected_at": c["connected_at"],
                "rows": n,
                "snapshot_sha256": h.hexdigest(),
            }
        )
    return out


def _methodology() -> dict:
    return {
        "engine": "HerdProof GAF-beef port v0.1 (demo; simplified from the AIA EAP beef calculator)",
        "gwp": "IPCC AR5 GWP100 (CH4 28, N2O 265)",
        "enteric": "DMI (Minson & McDonald) x 20.7 g CH4/kg DMI (Charmley et al. 2016)",
        "intensity": "(Scope 1 + Scope 2 + purchased-cattle Scope 3) / liveweight produced",
        "pcaf": "PCAF Global Standard Part A, business loans: 3b/3a sector proxies (illustrative factors), 2b production "
        "proxy, 1b farm-reported (multi-source reconciled with a clear land-use check is flagged assurance-ready); "
        "1a only after independent third-party verification",
        "financed_emissions": "Attributed Scope 1 + 2 only; purchased-cattle Scope 3 is in the footprint but not attributed",
        "attribution": "Equations and constants adapted from AIA Environmental Accounting Platform emissions-calculators "
        "v3.0.2 (Agricultural Innovation Australia, CC BY 4.0); unofficial derivative, not validated by AIA. See NOTICE.",
        "limitations": [
            "Demo data are synthetic",
            "Seasons approximated by FY quarters",
            "Plantings sequestration uses flat rates, not FullCAM",
            "Not a certified calculation",
        ],
    }


def _facts(fp: dict, rec: dict, defo: dict, farm: dict) -> dict:
    b = fp["benchmark"]
    return {
        "farm": farm["farm_name"],
        "region": f"{farm['region_name']}, {farm['state']}",
        "period": "FY2025-26",
        "lw_produced_t": fp["lw_produced_kg"] / 1000,
        "gross_t": fp["gross_t"],
        "scope1_t": fp["scope1_t"],
        "scope2_t": fp["scope2_t"],
        "scope3_t": fp["scope3_purchased_t"],
        "intensity": fp["intensity_kg_per_kg_lw"],
        "enteric_share": 100 * fp["enteric_t"] / fp["gross_t"],
        "benchmark": b
        and {
            "name": f"{b['benchmark_name']} ({b['level']})",
            "median": b["median_intensity"],
            "n_farms": b["n_farms"],
            "pct_vs_median": b["pct_vs_median"],
        },
        "reconciliation": {
            "confidence": rec["confidence"],
            "n_fail": rec["n_fail"],
            "n_warn": rec["n_warn"],
            "sources": [s for s in ("agriwebb", "nlis", "satellite") if rec[f"has_{s}"]],
            "failed_checks": [c["label"] for c in rec["checks"] if c["status"] == "fail"],
        },
        "deforestation": {"status": defo["status"], "loss_ha": defo["post_cutoff_loss_ha"]},
    }


def _register(con: Con, pack: dict, lender_id: str | None) -> dict:
    con.execute(REGISTRY_DDL)
    i = pack["integrity"]
    con.execute(
        "insert or replace into app.evidence_packs values (?, ?, ?, ?, ?, ?, ?)",
        [
            i["pack_id"],
            pack["farm"]["farm_id"],
            pack["pack_type"],
            lender_id,
            i["content_hash"],
            pack["issued_at"],
            json.dumps(pack),
        ],
    )
    return pack


def _header(farm: dict, pack_type: str) -> dict:
    return {
        "schema": SCHEMA,
        "pack_type": pack_type,
        "issued_at": settings.as_at.isoformat(),
        "reporting_period": services.period(),
        "farm": {k: farm[k] for k in ("farm_id", "farm_name", "pic", "region_name", "state")},
    }


def lender_pack(con: Con, lender_id: str, farm_id: str) -> dict:
    detail = services.borrower_detail(con, lender_id, farm_id)  # raises ConsentRequired without lender_share consent
    farm = services.farm(con, farm_id)
    loan, fp, rec, defo = detail["loan"], detail["footprint"], detail["reconciliation"], detail["deforestation"]
    grant = next(c for c in farm["consents"] if c["purpose"] == f"lender_share:{lender_id}")
    herd = "herd_detail" in (grant["scopes"] or [])  # class/flow detail only with the optional herd_detail scope
    hidden = ("gaf_inputs", "benchmark", "farm_id") + (() if herd else ("herd_flows",))
    pcaf = {
        "before": loan["baseline_score"],
        "before_option": loan["baseline_option"],
        "before_financed_t": loan["baseline_financed_t"],
        "after": loan["connected_score"],
        "after_option": loan["connected_option"],
        "assurance_ready": loan["assurance_ready"],
        "financed_t": loan["connected_financed_t"],
        "attribution_factor": loan["attribution_factor"],
        "outstanding_aud": loan["outstanding_aud"],
    }
    facts = {**_facts(fp, rec, defo, farm), "pcaf": pcaf}
    pack = {
        **_header(farm, "lender_borrower"),
        "audience": {"lender_id": lender_id, "lender_name": loan["lender_name"], "facility_id": loan["facility_id"]},
        "consent": {
            "consent_id": grant["consent_id"],
            "purpose": grant["purpose"],
            "scopes": grant["scopes"],
            "granted_at": grant["granted_at"],
            "basis": "Australian Farm Data Code v2",
        },
        "sources": _snapshots(con, farm),
        "footprint": {k: v for k, v in fp.items() if k not in hidden},
        **({"gaf_inputs": fp["gaf_inputs"]} if herd else {}),
        "benchmark": fp["benchmark"],
        "reconciliation": rec,
        "deforestation": defo,
        "pcaf": pcaf,
        "transition_levers": services.levers(con, farm_id),
        "methodology": _methodology(),
        "narrative": narrative.write("lender", facts),
    }
    return _register(con, seal(pack), lender_id)


def grazier_report(con: Con, farm_id: str) -> dict:
    farm = services.farm(con, farm_id)
    fp, rec, defo = (
        services.footprint(con, farm_id),
        services.reconciliation(con, farm_id),
        services.deforestation(con, farm_id),
    )
    levers = services.levers(con, farm_id)
    pack = {
        **_header(farm, "grazier_report"),
        "audience": {"grazier": farm["farm_name"]},
        "sources": _snapshots(con, farm),
        "footprint": {k: v for k, v in fp.items() if k not in ("gaf_inputs", "benchmark", "farm_id")},
        "benchmark": fp["benchmark"],
        "reconciliation": {k: rec[k] for k in ("confidence", "coverage", "n_fail", "n_warn")},
        "deforestation": {k: defo[k] for k in ("status", "post_cutoff_loss_ha", "cutoff_date")},
        "levers": levers,
        "methodology": _methodology(),
        "narrative": narrative.write("grazier", {**_facts(fp, rec, defo, farm), "levers": levers}),
    }
    return _register(con, seal(pack), None)


def owner(con: Con, pack_id: str) -> tuple[str, str | None]:
    con.execute(REGISTRY_DDL)
    row = con.execute("select farm_id, lender_id from app.evidence_packs where pack_id = ?", [pack_id]).fetchone()
    if not row:
        raise services.NotFound(pack_id)
    return row[0], row[1]


def get(con: Con, pack_id: str) -> dict:
    """Full pack while consent holds; a body-less stub once the borrower revokes lender sharing."""
    farm_id, lender_id = owner(con, pack_id)
    body, digest = con.execute(
        "select body, content_hash from app.evidence_packs where pack_id = ?", [pack_id]
    ).fetchone()
    if lender_id and not consent.has_consent(con, farm_id, f"lender_share:{lender_id}"):
        return {
            "pack_id": pack_id,
            "status": "revoked",
            "content_hash": digest,
            "detail": "The borrower withdrew consent; content is withheld. The hash stays verifiable via /verify.",
        }
    return json.loads(body)
