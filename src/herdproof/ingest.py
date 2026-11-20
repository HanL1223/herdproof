"""Extract-load: HerdProof app records plus consented source data into the DuckDB raw schema via NDJSON landing files."""

import json
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import duckdb

from herdproof import consent
from herdproof.adapters import ADAPTERS, FarmRef, fixture_adapters
from herdproof.config import settings
from herdproof.consent import LEDGER_DDL

CORE = {
    "hp_farms": (
        "farms.json",
        {
            "farm_id": "VARCHAR",
            "name": "VARCHAR",
            "region": "VARCHAR",
            "state": "VARCHAR",
            "pic": "VARCHAR",
            "agriwebb_farm_id": "VARCHAR",
            "lat": "DOUBLE",
            "lon": "DOUBLE",
            "breed": "VARCHAR",
        },
    ),
    "hp_regions": (
        "regions.json",
        {
            "code": "VARCHAR",
            "name": "VARCHAR",
            "state": "VARCHAR",
            "north_of_capricorn": "BOOLEAN",
            "rainfall_above_600": "BOOLEAN",
            "zone": "VARCHAR",
            "lat": "DOUBLE",
            "lon": "DOUBLE",
        },
    ),
    "hp_farm_inputs": (
        "farm_inputs.json",
        {
            "farm_id": "VARCHAR",
            "diesel_l": "DOUBLE",
            "petrol_l": "DOUBLE",
            "electricity_kwh": "DOUBLE",
            "renewable_fraction": "DOUBLE",
            "fertiliser_n_kg": "DOUBLE",
            "urea_kg": "DOUBLE",
            "lime_t": "DOUBLE",
            "plantings_ha": "DOUBLE",
        },
    ),
    "hp_lenders": ("lenders.json", {"lender_id": "VARCHAR", "name": "VARCHAR", "segment": "VARCHAR"}),
    "hp_loans": (
        "loans.json",
        {
            "lender_id": "VARCHAR",
            "farm_id": "VARCHAR",
            "facility_id": "VARCHAR",
            "outstanding_aud": "DOUBLE",
            "total_assets_aud": "DOUBLE",
            "revenue_aud": "DOUBLE",
            "declared_head": "INTEGER",
        },
    ),
    "hp_processors": ("processors.json", {"processor_id": "VARCHAR", "name": "VARCHAR", "pic": "VARCHAR"}),
    "hp_connections": (
        "connections.json",
        {"farm_id": "VARCHAR", "source": "VARCHAR", "auth_type": "VARCHAR", "connected_at": "TIMESTAMPTZ"},
    ),
}


def _snake(key: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", key).lower()


def _land(con: duckdb.DuckDBPyConnection, table: str, columns: dict[str, str], rows: list[dict], landing: Path) -> int:
    path = landing / f"{table}.ndjson"
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps({c: row.get(c) for c in columns}) + "\n")
    cols = ", ".join(f"{c} {t}" for c, t in columns.items())
    spec = ", ".join(f"'{c}': '{t}'" for c, t in columns.items())
    con.execute(f"create or replace table raw.{table} ({cols})")
    if rows:
        src = path.as_posix().replace("'", "''")
        con.execute(
            f"insert into raw.{table} select * from read_json('{src}', format='newline_delimited', columns={{{spec}}})"
        )
    return len(rows)


def run(fixtures_dir: Path | None = None, db_path: Path | None = None) -> dict[str, int]:
    fixtures_dir, db_path = fixtures_dir or settings.fixtures_dir, db_path or settings.db_path
    landing = settings.landing_dir
    landing.mkdir(parents=True, exist_ok=True)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    counts: dict[str, int] = {}
    with duckdb.connect(str(db_path)) as con:
        con.execute("create schema if not exists raw")
        core = {}
        for table, (file, columns) in CORE.items():
            data = json.loads((fixtures_dir / "herdproof" / file).read_text(encoding="utf-8"))
            core[table] = [{_snake(k): v for k, v in d.items()} for d in data]
            counts[table] = _land(con, table, columns, core[table], landing)
        _load_consents(con, fixtures_dir / "herdproof" / "consents.json")

        farms = {f["farm_id"]: FarmRef(f["farm_id"], f["pic"], f["agriwebb_farm_id"]) for f in core["hp_farms"]}
        adapters = fixture_adapters(fixtures_dir)
        rows: dict[str, list[dict]] = defaultdict(list)
        for conn in core["hp_connections"]:  # only farms that connected a source are ever extracted
            for table, batch in adapters[conn["source"]].extract(farms[conn["farm_id"]]).items():
                rows[table] += batch
        for adapter in ADAPTERS.values():
            for table, columns in adapter.schema.items():
                counts[table] = _land(con, table, columns, rows[table], landing)
    return counts


def _load_consents(con: duckdb.DuckDBPyConnection, path: Path) -> None:
    con.execute("drop schema if exists app cascade")  # a build resets the demo's live application state
    con.execute(LEDGER_DDL)
    for c in json.loads(path.read_text(encoding="utf-8")):
        consent.grant(con, c["farmId"], c["purpose"], c["scopes"], at=datetime.fromisoformat(c["grantedAt"]))
