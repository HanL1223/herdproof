"""FastAPI service over the warehouse.

Auth is a demo stub: callers state who they are in `X-Demo-Principal` (farm:F001, lender:L1, processor:P1).
"""

import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Annotated

import duckdb
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from herdproof import consent, evidence, services
from herdproof.config import settings

app = FastAPI(
    title="HerdProof API",
    version="0.1.0",
    description="Consented herd and land data turned into reconciled, assurance-ready Scope 3 evidence (demo). "
    "Auth is a stub: send `X-Demo-Principal: farm:F001 | lender:L1 | processor:P1`.",
)
_lock = threading.Lock()


@contextmanager
def db() -> Iterator[duckdb.DuckDBPyConnection]:
    # One short-lived connection per request, so CLI commands can use the file while the server is idle.
    if not settings.db_path.exists():
        raise HTTPException(503, "Warehouse not found: run `uv run herdproof build` first")
    with _lock:
        try:
            con = duckdb.connect(str(settings.db_path))
        except duckdb.IOException as e:
            raise HTTPException(503, "Warehouse is locked by a build or export; retry shortly") from e
        try:
            yield con
        finally:
            con.close()


def principal(x_demo_principal: Annotated[str | None, Header()] = None) -> tuple[str, str]:
    kind, _, ident = (x_demo_principal or "").partition(":")
    if kind not in ("farm", "lender", "processor") or not ident:
        raise HTTPException(401, "Send X-Demo-Principal: farm:<id> | lender:<id> | processor:<id> (demo auth stub)")
    return kind, ident


Principal = Annotated[tuple[str, str], Depends(principal)]


def require(who: tuple[str, str], kind: str, ident: str) -> None:
    if who != (kind, ident):
        raise HTTPException(403, f"{who[0]}:{who[1]} may not access {kind}:{ident}")


@app.exception_handler(services.NotFound)
def _not_found(_, exc: services.NotFound) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(services.ConsentRequired)
def _forbidden(_, exc: services.ConsentRequired) -> JSONResponse:
    return JSONResponse(status_code=403, content={"detail": str(exc)})


class ConsentRequest(BaseModel):
    purpose: str = Field(examples=["lender_share:L1", "regional_benchmark", "processor_cohort"])
    scopes: list[str] = ["footprint", "reconciliation", "deforestation"]


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "as_at": settings.as_at.isoformat()}


@app.get("/farms/{farm_id}")
def get_farm(farm_id: str, who: Principal) -> dict:
    require(who, "farm", farm_id)
    with db() as con:
        return services.farm(con, farm_id)


@app.get("/connect/{source}/callback")
def oauth_callback(source: str, farm_id: str, code: str, who: Principal) -> dict:
    """Mock OAuth2 authorization-code callback (AgriWebb) or PIC authorisation (NLIS); data lands on the next build."""
    require(who, "farm", farm_id)
    if source not in ("agriwebb", "nlis", "satellite"):
        raise HTTPException(400, f"Unknown source {source}")
    with db() as con:
        services.farm(con, farm_id)
        con.execute("delete from raw.hp_connections where farm_id = ? and source = ?", [farm_id, source])
        con.execute(
            "insert into raw.hp_connections values (?, ?, ?, ?)",
            [
                farm_id,
                source,
                "oauth2_authorization_code" if source == "agriwebb" else "licensed",
                datetime.now(UTC),
            ],
        )
    return {"farm_id": farm_id, "source": source, "status": "connected", "auth_code_received": bool(code)}


@app.get("/farms/{farm_id}/consents")
def list_consents(farm_id: str, who: Principal) -> list[dict]:
    require(who, "farm", farm_id)
    with db() as con:
        return consent.active(con, farm_id)


@app.get("/farms/{farm_id}/consents/history")
def consent_history(farm_id: str, who: Principal) -> list[dict]:
    require(who, "farm", farm_id)
    with db() as con:
        return consent.history(con, farm_id)


@app.post("/farms/{farm_id}/consents", status_code=201)
def grant_consent(farm_id: str, req: ConsentRequest, who: Principal) -> dict:
    require(who, "farm", farm_id)
    with db() as con:
        services.farm(con, farm_id)
        try:
            return {"consent_id": consent.grant(con, farm_id, req.purpose, req.scopes)}
        except ValueError as e:
            raise HTTPException(400, str(e)) from e


@app.delete("/farms/{farm_id}/consents/{purpose}")
def revoke_consent(farm_id: str, purpose: str, who: Principal) -> dict:
    require(who, "farm", farm_id)
    with db() as con:
        try:
            return {"revoked": consent.revoke(con, farm_id, purpose)}
        except ValueError as e:
            raise HTTPException(400, str(e)) from e


@app.get("/farms/{farm_id}/footprint")
def get_footprint(farm_id: str, who: Principal) -> dict:
    require(who, "farm", farm_id)
    with db() as con:
        return services.footprint(con, farm_id)


@app.get("/farms/{farm_id}/levers")
def get_levers(farm_id: str, who: Principal) -> list[dict]:
    require(who, "farm", farm_id)
    with db() as con:
        return services.levers(con, farm_id)


@app.get("/farms/{farm_id}/reconciliation")
def get_reconciliation(farm_id: str, who: Principal) -> dict:
    require(who, "farm", farm_id)
    with db() as con:
        return services.reconciliation(con, farm_id)


@app.get("/farms/{farm_id}/deforestation")
def get_deforestation(farm_id: str, who: Principal) -> dict:
    require(who, "farm", farm_id)
    with db() as con:
        return services.deforestation(con, farm_id)


@app.get("/farms/{farm_id}/report")
def get_grazier_report(farm_id: str, who: Principal) -> dict:
    require(who, "farm", farm_id)
    with db() as con:
        return evidence.grazier_report(con, farm_id)


@app.get("/benchmarks")
def get_benchmarks(who: Principal) -> list[dict]:
    with db() as con:
        return services.benchmarks(con)


@app.get("/lenders/{lender_id}/portfolio")
def get_portfolio(lender_id: str, who: Principal) -> dict:
    require(who, "lender", lender_id)
    with db() as con:
        return services.lender_portfolio(con, lender_id)


@app.post("/lenders/{lender_id}/borrowers/{farm_id}/evidence-pack", status_code=201)
def issue_pack(lender_id: str, farm_id: str, who: Principal) -> dict:
    require(who, "lender", lender_id)
    with db() as con:
        return evidence.lender_pack(con, lender_id, farm_id)


@app.get("/packs/{pack_id}")
def get_pack(pack_id: str, who: Principal) -> dict:
    with db() as con:
        farm_id, lender_id = evidence.owner(con, pack_id)
        if who not in (("farm", farm_id), ("lender", lender_id)):
            raise HTTPException(403, f"{who[0]}:{who[1]} may not access pack {pack_id}")
        return evidence.get(con, pack_id)


@app.post("/verify")
def verify_pack(pack: dict) -> dict:
    """Public: anyone holding a pack can check its hash, registration and whether consent is still active."""
    with db() as con:
        return evidence.verify(pack, con)


@app.get("/processors/{processor_id}/cohort")
def get_cohort(processor_id: str, who: Principal) -> dict:
    require(who, "processor", processor_id)
    with db() as con:
        return services.processor_cohort(con, processor_id)
