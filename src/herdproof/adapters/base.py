"""Common contract for source adapters: each lands typed raw tables for one consented farm."""

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, ClassVar, Protocol

Rows = list[dict[str, Any]]


@dataclass(frozen=True)
class FarmRef:
    farm_id: str
    pic: str
    agriwebb_farm_id: str


class Transport(Protocol):
    def __call__(self, key: str, operation: str | None = None, **params: Any) -> dict: ...


class FixtureTransport:
    """Serves recorded API payloads from disk; production swaps in an HTTP transport."""

    def __init__(self, directory: Path):
        self.directory = directory
        self._cache: dict[str, dict] = {}

    def __call__(self, key: str, operation: str | None = None, **params: Any) -> dict:
        if key not in self._cache:
            self._cache = {key: json.loads((self.directory / f"{key}.json").read_text(encoding="utf-8"))}
        payload = self._cache[key]
        return payload[operation] if operation else payload


class SourceAdapter(ABC):
    source: ClassVar[str]
    schema: ClassVar[dict[str, dict[str, str]]]  # raw table -> column -> DuckDB type

    def __init__(self, transport: Transport):
        self.transport = transport

    @abstractmethod
    def extract(self, farm: FarmRef) -> dict[str, Rows]:
        """Return rows per raw table for one farm."""


def ms_to_date(value: float | None) -> str | None:
    return None if value is None else datetime.fromtimestamp(value / 1000, tz=UTC).date().isoformat()
