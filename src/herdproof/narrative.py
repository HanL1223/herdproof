"""Narratives for evidence packs: Claude when ANTHROPIC_API_KEY is set, deterministic templates otherwise."""

import json
import os
from typing import Literal, Protocol

from herdproof.config import settings

Kind = Literal["lender", "grazier"]
SOURCE_NAMES = {"agriwebb": "AgriWebb", "nlis": "NLIS", "satellite": "satellite pasture data"}

SYSTEM = {
    "lender": "You write the summary section of a borrower emissions evidence pack for an Australian agricultural lender's "
    "credit and sustainability team. Use only the facts in the JSON provided; never invent or recompute numbers. "
    "Be precise and neutral, under 170 words, plain text, no headings. Mention the PCAF score change, "
    "reconciliation confidence and any failed checks, and the deforestation status.",
    "grazier": "You write a short plain-English note to an Australian cattle grazier about their farm's emissions report. "
    "Use only the facts in the JSON provided; never invent numbers. Friendly, practical, no jargon, under 170 words, "
    "plain text. Explain what the intensity number means, how they compare to the benchmark, and the top levers.",
}


class NarrativeWriter(Protocol):
    name: str

    def write(self, kind: Kind, facts: dict) -> str: ...


class TemplateWriter:
    name = "template"

    def write(self, kind: Kind, facts: dict) -> str:
        return _lender(facts) if kind == "lender" else _grazier(facts)


class ClaudeWriter:
    def __init__(self, model: str):
        import anthropic  # optional dependency: uv sync --extra ai

        self.client, self.name = anthropic.Anthropic(), model

    def write(self, kind: Kind, facts: dict) -> str:
        msg = self.client.messages.create(
            model=self.name,
            max_tokens=600,
            system=SYSTEM[kind],
            messages=[{"role": "user", "content": json.dumps(facts)}],
        )
        return "".join(b.text for b in msg.content if b.type == "text").strip()


def writer() -> NarrativeWriter:
    if os.getenv("ANTHROPIC_API_KEY"):
        try:
            return ClaudeWriter(settings.llm_model)
        except ImportError:
            pass
    return TemplateWriter()


def write(kind: Kind, facts: dict) -> dict:
    w = writer()
    try:
        return {"text": w.write(kind, facts), "generator": w.name}
    except Exception:  # any LLM failure falls back so packs are always issued
        return {"text": TemplateWriter().write(kind, facts), "generator": "template"}


def _bench_phrase(f: dict) -> str:
    b = f.get("benchmark")
    if not b:
        return "No benchmark comparison is included (the farm has not joined the regional benchmark, or none is published yet)."
    direction = "below" if b["pct_vs_median"] < 0 else "above"
    return (
        f"That is {abs(b['pct_vs_median']):.0f}% {direction} the {b['name']} median of {b['median']:.1f} "
        f"({b['n_farms']} consenting farms)."
    )


def _lender(f: dict) -> str:
    r, p, d = f["reconciliation"], f["pcaf"], f["deforestation"]
    flags = f" (failed: {'; '.join(r['failed_checks'])})" if r["failed_checks"] else ""
    loss = f" ({d['loss_ha']:.0f} ha woody loss since cut-off)" if d["status"] == "review" else ""
    verified_note = (
        (
            " Score 1 here means multi-source reconciled and assurance-ready; an independent limited-assurance "
            "sign-off is still required before it is reported as verified."
        )
        if p["after"] == 1
        else ""
    )
    return (
        f"{f['farm']} ({f['region']}) produced {f['lw_produced_t']:.0f} t liveweight in {f['period']} with gross emissions of "
        f"{f['gross_t']:.0f} t CO2e (Scope 1: {f['scope1_t']:.0f} t, Scope 2: {f['scope2_t']:.0f} t, purchased-cattle "
        f"Scope 3: {f['scope3_t']:.0f} t), an intensity of {f['intensity']:.1f} kg CO2e/kg LW. {_bench_phrase(f)} "
        f"Herd records were reconciled against {', '.join(SOURCE_NAMES[s] for s in r['sources'])}: confidence {r['confidence']:.0f}/100, "
        f"{r['n_fail']} failed and {r['n_warn']} warning checks{flags}. "
        f"Deforestation check against the 31 Dec 2020 cut-off: {d['status'].replace('_', ' ')}{loss}. "
        f"PCAF data quality improves from {p['before']} (option {p['before_option']}) to {p['after']} (option "
        f"{p['after_option']}); attributed financed emissions are {p['financed_t']:.0f} t CO2e at an attribution factor of "
        f"{p['attribution_factor']:.2f}.{verified_note}"
    )


def _grazier(f: dict) -> str:
    levers = " ".join(
        f"{i + 1}) {lv['title']} ({lv['intensity_change_pct']:+.1f}%)." for i, lv in enumerate(f["levers"][:3])
    )
    return (
        f"In {f['period']} {f['farm']} produced {f['lw_produced_t']:.0f} tonnes of liveweight. Producing it released about "
        f"{f['gross_t']:.0f} tonnes of CO2e, {f['enteric_share']:.0f}% of it methane from digestion. That works out at "
        f"{f['intensity']:.1f} kg CO2e for every kg of liveweight. {_bench_phrase(f)} "
        f"Your AgriWebb records line up with NLIS movements and satellite pasture data (confidence "
        f"{f['reconciliation']['confidence']:.0f}/100), so a lender or buyer can rely on them without another survey. "
        f"The biggest levers for your operation: {levers} Most of them also lift kilograms sold, so they pay their own way."
    )
