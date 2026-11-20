"""Command line entry point: `uv run herdproof <command>`."""

import argparse
import json
import sys
from pathlib import Path


def _build(args: argparse.Namespace) -> None:
    from herdproof import ingest, synth, transform

    if not args.skip_generate:
        print(f"Generating fixtures -> {synth.generate()}")
    counts = ingest.run()
    print("Landed raw tables: " + ", ".join(f"{k}={v}" for k, v in counts.items()))
    transform.run()
    print("dbt build complete (staging -> intermediate -> marts)")


def _export(_: argparse.Namespace) -> None:
    from herdproof import export

    out = export.run()
    print(f"Demo written to {out['path']} ({out['bytes'] / 1024:.0f} KB)")


def _serve(args: argparse.Namespace) -> None:
    import uvicorn

    uvicorn.run("herdproof.api:app", host=args.host, port=args.port)


def _pack(args: argparse.Namespace) -> None:
    import duckdb

    from herdproof import evidence
    from herdproof.config import settings

    with duckdb.connect(str(settings.db_path)) as con:
        pack = (
            evidence.lender_pack(con, args.lender, args.farm)
            if args.lender
            else evidence.grazier_report(con, args.farm)
        )
    text = json.dumps(pack, indent=2, ensure_ascii=False)
    if args.out:  # write UTF-8 directly; PowerShell `>` would re-encode the JSON
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"{pack['integrity']['pack_id']} written to {args.out}")
    else:
        print(text)


def _verify(args: argparse.Namespace) -> None:
    from herdproof import evidence

    result = evidence.verify(json.loads(Path(args.path).read_text(encoding="utf-8-sig")))
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["valid"] else 1)


def main() -> None:
    parser = argparse.ArgumentParser(prog="herdproof", description="HerdProof demo backend")
    sub = parser.add_subparsers(dest="command", required=True)
    b = sub.add_parser("build", help="generate fixtures, ingest consented sources, run dbt")
    b.add_argument("--skip-generate", action="store_true", help="reuse existing fixtures")
    b.set_defaults(func=_build)
    sub.add_parser("export-demo", help="write demo/index.html with embedded data").set_defaults(func=_export)
    s = sub.add_parser("serve", help="run the FastAPI service")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8000)
    s.set_defaults(func=_serve)
    p = sub.add_parser("pack", help="issue an evidence pack (lender pack if --lender, else grazier report)")
    p.add_argument("--farm", required=True)
    p.add_argument("--lender")
    p.add_argument("--out", help="write the pack to this file (UTF-8)")
    p.set_defaults(func=_pack)
    v = sub.add_parser("verify", help="verify an evidence pack JSON file")
    v.add_argument("path")
    v.set_defaults(func=_verify)
    args = parser.parse_args()
    args.func(args)
