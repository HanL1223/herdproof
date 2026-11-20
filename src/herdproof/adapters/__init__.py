"""Source adapters keyed by connection source name."""

from pathlib import Path

from herdproof.adapters.agriwebb import AgriWebbAdapter
from herdproof.adapters.base import FarmRef, FixtureTransport, SourceAdapter
from herdproof.adapters.nlis import NlisAdapter
from herdproof.adapters.satellite import SatelliteAdapter

ADAPTERS: dict[str, type[SourceAdapter]] = {a.source: a for a in (AgriWebbAdapter, NlisAdapter, SatelliteAdapter)}


def fixture_adapters(fixtures_dir: Path) -> dict[str, SourceAdapter]:
    return {name: cls(FixtureTransport(fixtures_dir / name)) for name, cls in ADAPTERS.items()}


__all__ = ["ADAPTERS", "FarmRef", "SourceAdapter", "fixture_adapters"]
