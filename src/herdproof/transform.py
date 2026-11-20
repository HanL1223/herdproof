"""Runs the dbt project (seeds + models) against the local DuckDB warehouse."""

import os
import subprocess
import sys

from herdproof.config import settings

# dbt runs in a child process so its DuckDB connection is released when the build ends.
DBT = "import sys; from dbt.cli.main import cli; sys.exit(cli())"


def run(select: str | None = None) -> None:
    wd = str(settings.warehouse_dir)
    env = {**os.environ, "HERDPROOF_DUCKDB": str(settings.db_path.resolve())}
    args = ["build", "--project-dir", wd, "--profiles-dir", wd, "--quiet"] + (["--select", select] if select else [])
    if subprocess.run([sys.executable, "-c", DBT, *args], env=env).returncode:
        raise RuntimeError("dbt build failed; see warehouse/logs/dbt.log")
