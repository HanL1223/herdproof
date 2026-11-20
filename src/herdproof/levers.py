"""Quantified improvement levers: first-order what-ifs on the farm's own footprint (indicative, not a plan)."""

SEQ_RATE = {"tropical": 3.0, "temperate": 5.0}  # t CO2e/ha/yr, mirrors ref_emission_factors


def _lever(
    fp: dict,
    lever_id: str,
    title: str,
    how: str,
    effort: str,
    d_emissions: float = 0.0,
    d_lw: float = 0.0,
    d_seq: float = 0.0,
) -> dict:
    # Sequestration levers are judged on net intensity; all others on gross intensity.
    lw = fp["lw_produced_kg"]
    start = fp["gross_t"] - (fp["sequestration_t"] if d_seq else 0)
    base, new = start * 1000 / lw, (start + d_emissions - d_seq) * 1000 / (lw + d_lw)
    return {
        "id": lever_id,
        "title": title,
        "how": how,
        "effort": effort,
        "emissions_change_t": round(d_emissions - d_seq, 1),
        "liveweight_change_kg": round(d_lw),
        "new_intensity": round(new, 2),
        "intensity_change_pct": round(100 * (new / base - 1), 1),
        "metric": "net" if d_seq else "gross",
    }


def improvement_levers(fp: dict, area_ha: float, zone: str, top: int = 4) -> list[dict]:
    inputs = [r for r in fp["gaf_inputs"] if r["head"] > 0]

    def avg_kg(classes: set[str]) -> float:
        sel = [r for r in inputs if r["gaf_class"] in classes]
        return sum(r["liveweight_kg"] * r["head"] for r in sel) / max(sum(r["head"] for r in sel), 1e-9)

    cows = sum(r["head"] for r in inputs if r["gaf_class"] == "cowsGt2") / 4
    weaner_kg = avg_kg({"steersLt1", "heifersLt1"}) or 200
    herd_kg = avg_kg({r["gaf_class"] for r in inputs} - {"calves"})
    levers = [
        _lever(
            fp,
            "weaning",
            "Lift weaning rate by 5 points",
            "Pregnancy-test and cull empty cows, match stocking to feed, tighten the calving window.",
            "medium",
            d_emissions=0.05 * cows * 0.4,
            d_lw=0.05 * cows * weaner_kg,
        ),
        _lever(
            fp,
            "mortality",
            "Halve breeder and calf losses",
            "Phosphorus and dry-season supplements, better water point coverage.",
            "medium",
            d_lw=fp["herd_flows"]["deaths"] / 2 * herd_kg * 0.6,
        ),
        _lever(
            fp,
            "fuel",
            "Cut diesel use by 15%",
            "Route planning, telemetry on water runs, pump and vehicle servicing.",
            "low",
            d_emissions=-0.15 * fp["fuel_t"],
        ),
        _lever(
            fp,
            "plantings",
            "Plant 1% of the property to shelterbelts",
            "Shade and shelter belts on low-value country; sequestration is reported separately from gross.",
            "high",
            d_seq=0.01 * area_ha * SEQ_RATE[zone],
        ),
    ]
    if fp["scope2_t"] > 0:
        levers.append(
            _lever(
                fp,
                "solar",
                "Move pumps and sheds to solar",
                "Solar bores and a shed array remove most Scope 2.",
                "low",
                d_emissions=-0.9 * fp["scope2_t"],
            )
        )
    if fp["fertiliser_n2o_t"] > 0:
        levers.append(
            _lever(
                fp,
                "nitrogen",
                "Trim synthetic nitrogen by 20%",
                "Soil test and lift legumes in the pasture mix.",
                "low",
                d_emissions=-0.2 * (fp["fertiliser_n2o_t"] + fp["urea_lime_co2_t"]),
            )
        )
    return sorted(levers, key=lambda x: x["intensity_change_pct"])[:top]
