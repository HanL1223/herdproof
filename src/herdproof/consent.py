"""Purpose-bound consent ledger: append-only grant/revoke events, with current state derived as a view."""

from datetime import UTC, datetime

import duckdb

PURPOSES = ("regional_benchmark", "processor_cohort", "lender_share")
SCOPES = ("footprint", "reconciliation", "deforestation", "herd_detail")

LEDGER_DDL = """
create schema if not exists app;
create sequence if not exists app.consent_event_seq;
create table if not exists app.consent_events (
    event_id bigint primary key default nextval('app.consent_event_seq'), consent_id varchar not null,
    farm_id varchar not null, purpose varchar not null, action varchar not null check (action in ('grant', 'revoke')),
    scopes varchar[], event_at timestamptz not null, basis varchar
);
create or replace view app.consent_ledger as
select g.consent_id, g.farm_id, g.purpose, g.scopes, g.event_at as granted_at,
       (select min(r.event_at) from app.consent_events r where r.farm_id = g.farm_id and r.purpose = g.purpose
          and r.action = 'revoke' and r.event_id > g.event_id) as revoked_at,
       g.basis
from app.consent_events g
where g.action = 'grant'
qualify row_number() over (partition by g.farm_id, g.purpose order by g.event_id desc) = 1;"""


def validate(con: duckdb.DuckDBPyConnection, purpose: str, scopes: list[str] | None = None) -> None:
    kind, _, target = purpose.partition(":")
    if kind not in PURPOSES or (kind == "lender_share") != bool(target):
        raise ValueError(f"Unknown consent purpose: {purpose}")
    if target and not con.execute("select 1 from raw.hp_lenders where lender_id = ?", [target]).fetchone():
        raise ValueError(f"Unknown lender: {target}")
    if bad := sorted(set(scopes or []) - set(SCOPES)):
        raise ValueError(f"Unknown scopes: {bad}")


def _event(
    con: duckdb.DuckDBPyConnection,
    farm_id: str,
    purpose: str,
    action: str,
    scopes: list[str] | None,
    at: datetime | None,
) -> str:
    consent_id = f"C-{farm_id}-{purpose.replace(':', '-')}"
    con.execute(
        "insert into app.consent_events (consent_id, farm_id, purpose, action, scopes, event_at, basis) "
        "values (?, ?, ?, ?, ?, ?, 'Australian Farm Data Code v2')",
        [consent_id, farm_id, purpose, action, scopes, at or datetime.now(UTC)],
    )
    return consent_id


def grant(
    con: duckdb.DuckDBPyConnection, farm_id: str, purpose: str, scopes: list[str], at: datetime | None = None
) -> str:
    validate(con, purpose, scopes)
    return _event(con, farm_id, purpose, "grant", scopes, at)


def revoke(con: duckdb.DuckDBPyConnection, farm_id: str, purpose: str) -> bool:
    validate(con, purpose)
    if not has_consent(con, farm_id, purpose):
        return False
    _event(con, farm_id, purpose, "revoke", None, None)
    return True


def has_consent(con: duckdb.DuckDBPyConnection, farm_id: str, purpose: str) -> bool:
    return (
        con.execute(
            "select count(*) from app.consent_ledger where farm_id = ? and purpose = ? and revoked_at is null",
            [farm_id, purpose],
        ).fetchone()[0]
        > 0
    )


def active(con: duckdb.DuckDBPyConnection, farm_id: str) -> list[dict]:
    rows = con.execute(
        "select consent_id, purpose, scopes, granted_at from app.consent_ledger where farm_id = ? and revoked_at is null order by purpose",
        [farm_id],
    ).fetchall()
    return [{"consent_id": r[0], "purpose": r[1], "scopes": r[2], "granted_at": r[3].isoformat()} for r in rows]


def history(con: duckdb.DuckDBPyConnection, farm_id: str) -> list[dict]:
    rows = con.execute(
        "select event_id, consent_id, purpose, action, scopes, event_at from app.consent_events where farm_id = ? order by event_id",
        [farm_id],
    ).fetchall()
    keys = ("event_id", "consent_id", "purpose", "action", "scopes", "event_at")
    return [{**dict(zip(keys, r, strict=True)), "event_at": r[5].isoformat()} for r in rows]
