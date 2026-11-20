"""Seeded synthetic generator: writes fixture payloads shaped like AgriWebb, ISC NLIS and satellite APIs."""

import json
import random
import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from itertools import accumulate
from pathlib import Path

from herdproof.config import settings

HERO_FARM = "F001"
EPOCH = date(2016, 7, 1)  # start of the daily growth curve


@dataclass(frozen=True)
class Region:
    code: str
    name: str
    state: str
    north_of_capricorn: bool
    rainfall_above_600: bool
    zone: str  # tropical | temperate
    ha_per_ae: tuple[float, float]
    land_value_ha: int
    lat: float
    lon: float


REGIONS = [
    Region("QLD-CH", "Central Highlands", "QLD", False, True, "tropical", (6, 10), 2600, -23.5, 148.2),
    Region("QLD-MD", "Maranoa & Darling Downs", "QLD", False, False, "tropical", (8, 14), 2200, -26.6, 149.2),
    Region("QLD-NW", "Gulf & North West", "QLD", True, False, "tropical", (20, 35), 650, -19.9, 140.5),
    Region("NT-BK", "Barkly & Katherine", "NT", True, False, "tropical", (25, 45), 320, -17.6, 134.2),
    Region("NSW-NE", "New England", "NSW", False, True, "temperate", (1.2, 2.2), 9000, -30.5, 151.6),
    Region("NSW-CW", "Central West", "NSW", False, False, "temperate", (1.8, 3.0), 5200, -33.0, 148.6),
    Region("VIC-WD", "Western District", "VIC", False, True, "temperate", (1.0, 1.8), 14000, -37.8, 142.2),
    Region("VIC-GP", "Gippsland", "VIC", False, True, "temperate", (0.9, 1.6), 15000, -38.1, 146.9),
]

ZONE = {
    "tropical": dict(
        cows=(140, 380),
        weaning=(0.60, 0.76),
        mortality=(0.025, 0.045),
        cow_kg=470,
        bull_kg=680,
        adg=(0.05, 0.25, 0.75, 0.40),
        calving=(date(2025, 10, 10), 80),
        price=3.3,
        sales=(date(2026, 5, 20),),
        culls=date(2026, 6, 10),
        steer_age=24 * 30,
        buy_on=date(2025, 11, 5),
        tsdm=(1800, 1200, 3000, 2600),
        cover=(62, 48, 80, 74),
        woody=(0.15, 0.35),
    ),
    "temperate": dict(
        cows=(60, 200),
        weaning=(0.82, 0.92),
        mortality=(0.010, 0.022),
        cow_kg=580,
        bull_kg=820,
        adg=(0.45, 1.05, 0.65, 0.55),
        calving=(date(2025, 7, 25), 60),
        price=3.8,
        sales=(date(2026, 2, 12),),
        culls=date(2026, 4, 8),
        steer_age=15 * 30,
        buy_on=date(2026, 3, 20),
        tsdm=(1400, 2600, 2000, 1500),
        cover=(86, 94, 88, 84),
        woody=(0.05, 0.15),
    ),
}

NORTH = dict(weaning=(0.48, 0.62), mortality=(0.05, 0.08), growth=0.7)

PROCESSORS = [
    dict(processorId="P1", name="Great Dividing Meat Co.", pic="QGDM0001", states=["QLD", "NT", "NSW"]),
    dict(processorId="P2", name="Southern Plains Processing", pic="3SPPR001", states=["VIC", "NSW"]),
]
LENDERS = [
    dict(lenderId="L1", name="Ironbark Rural Bank", segment="Regional bank", states=["QLD", "NSW", "NT"]),
    dict(lenderId="L2", name="Riverbend Agri Finance", segment="Mid-tier ag lender", states=["VIC", "NSW", "NT"]),
]
PREFIX = [
    "Kurrajong",
    "Wattle",
    "Ironbark",
    "Boree",
    "Brigalow",
    "Coolibah",
    "Mulga",
    "Gidgee",
    "Yarran",
    "Belah",
    "Myall",
    "Box Flat",
    "Redgum",
    "Stringybark",
    "Saltbush",
    "Bluegrass",
    "Mitchell",
    "Banksia",
    "Quandong",
    "Wilga",
    "Budda",
    "Tallowwood",
    "Blackbutt",
    "Grevillea",
    "Carbeen",
    "Leopardwood",
    "Bimble",
    "Kanooka",
]
SUFFIX = ["Downs", "Creek", "Park", "Station", "Plains", "Hill", "Vale", "Springs", "Flats", "Ridge"]
BREEDS = {
    "tropical": ["Brahman", "Droughtmaster", "Santa Gertrudis", "Brangus"],
    "temperate": ["Angus", "Hereford", "Angus x Hereford", "Shorthorn"],
}


@dataclass
class Animal:
    animal_id: str
    eid: str
    nlis_id: str
    sex: str
    steer: bool
    birth: date
    arrival: date
    arrival_kind: str
    gf: float
    af: float
    departure: date | None = None
    departure_kind: str | None = None
    buyer_pic: str | None = None
    vendor_pic: str | None = None
    records: list = field(default_factory=list)


def _ms(d: date) -> int:
    return int(datetime(d.year, d.month, d.day, tzinfo=UTC).timestamp() * 1000)


class FarmSim:
    """Simulates one farm's herd through the reporting period."""

    def __init__(self, rng: random.Random, farm: dict, region: Region, curve: list[float]):
        self.rng, self.farm, self.region, self.z = rng, farm, region, ZONE[region.zone]
        self.Y = curve
        self.mean_adg = sum(self.z["adg"]) / 4
        self.animals: list[Animal] = []
        self.serial = 0

    def _uid(self) -> str:
        return str(uuid.UUID(int=self.rng.getrandbits(128), version=4))

    def weight(self, a: Animal, d: date) -> float:
        age = (d - a.birth).days
        i, i200 = (d - EPOCH).days, max(0, (a.birth - EPOCH).days + 200)
        w = 35 + 0.8 * min(age, 200) + (a.gf * (self.Y[i] - self.Y[i200]) if age > 200 else 0)
        if a.steer:
            return round(min(w, 720), 1)
        mature = (self.z["bull_kg"] if a.sex == "Male" else self.z["cow_kg"]) * a.af
        swing = 0.6 * (self.Y[i] - self.mean_adg * i)
        return round(max(30.0, min(w, mature + swing)), 1)

    def new_animal(
        self, sex: str, birth: date, arrival: date, kind: str, steer: bool, tag_pic: str | None = None
    ) -> Animal:
        self.serial += 1
        tag_pic = tag_pic or self.farm["pic"]
        a = Animal(
            self._uid(),
            f"982 {self.rng.randrange(10**11, 10**12):012d}",
            f"{tag_pic}XBA{self.serial:05d}",
            sex,
            steer,
            birth,
            arrival,
            kind,
            gf=self.rng.gauss(1.0, 0.08) * self.farm["growth"],
            af=self.rng.gauss(1.0, 0.06),
        )
        self.animals.append(a)
        return a

    def run(self) -> None:
        r, z, p0, p1 = self.rng, self.z, settings.period_start, settings.period_end
        cows = self.farm["cows"]
        prior_calving = z["calving"][0].replace(year=z["calving"][0].year - 1)
        for _ in range(cows):
            self.new_animal("Female", p0 - timedelta(days=r.randint(830, 3650)), p0, "opening", False)
        for _ in range(max(2, cows // 35)):
            self.new_animal("Male", p0 - timedelta(days=r.randint(1100, 2900)), p0, "opening", False)
        for cohort_year, share in (
            (0, self.farm["weaning"]),
            (1, 0.95 * self.farm["weaning"] if self.region.zone == "tropical" else 0.18),
        ):
            base = prior_calving.replace(year=prior_calving.year - cohort_year)
            for _ in range(int(cows * share)):
                sex = r.choice(["Male", "Female"]) if cohort_year == 0 or self.region.zone == "tropical" else "Female"
                b = base + timedelta(days=r.randint(0, z["calving"][1]))
                self.new_animal(sex, b, p0, "opening", sex == "Male")
        self._births(cows)
        if self.farm["trader"]:
            for _ in range(int(cows * r.uniform(0.25, 0.45))):
                vendor = r.choice(["QBRD4471", "NBUY2210", "3TRD0042", "TSTN0098"])
                a = self.new_animal(
                    "Male", z["buy_on"] - timedelta(days=r.randint(220, 300)), z["buy_on"], "purchase", True, vendor
                )
                a.vendor_pic = vendor
        self._deaths()
        self._sales()
        for a in self.animals:
            if a.departure and a.departure > p1:
                a.departure, a.departure_kind = None, None

    def _births(self, cows: int) -> None:
        start, window = self.z["calving"]
        for _ in range(int(cows * (self.farm["weaning"] + 0.05))):
            b = start + timedelta(days=self.rng.randint(0, window))
            sex = self.rng.choice(["Male", "Female"])
            self.new_animal(sex, b, b, "birth", sex == "Male")

    def _deaths(self) -> None:
        p1 = settings.period_end
        for a in self.animals:
            days = (p1 - a.arrival).days
            extra = 0.04 if a.arrival_kind == "birth" else 0.0
            if self.rng.random() < self.farm["mortality"] * days / 365 + extra:
                a.departure, a.departure_kind = a.arrival + timedelta(days=self.rng.randint(1, max(1, days))), "death"

    def _sales(self) -> None:
        r, z = self.rng, self.z
        proc_id = "P2" if self.region.state == "VIC" or self.region.code == "NSW-CW" else "P1"
        proc = next(p for p in PROCESSORS if p["processorId"] == proc_id)
        self.farm["processor_pic"] = proc["pic"]

        def alive(a: Animal, d: date) -> bool:
            return a.arrival <= d and (a.departure is None or a.departure > d)

        for d in z["sales"]:
            for a in self.animals:
                if not alive(a, d):
                    continue
                age = (d - a.birth).days
                if a.steer and age >= z["steer_age"]:
                    buyer = proc["pic"] if r.random() < 0.65 else r.choice(["QFLT7781", "NFDL3302", "3BKG0510"])
                elif a.sex == "Female" and 420 <= age <= 760 and r.random() < 0.5:
                    buyer = r.choice(["QSYD0001", "NSYD0012", "3SYD0007"])
                else:
                    continue
                a.departure, a.departure_kind, a.buyer_pic = d + timedelta(days=r.randint(0, 3)), "sale", buyer
        d = z["culls"]
        breeders = sorted(
            (a for a in self.animals if alive(a, d) and not a.steer and (d - a.birth).days > 1500),
            key=lambda a: a.birth,
        )
        for a in breeders[: int(len(breeders) * r.uniform(0.12, 0.18))]:
            a.departure, a.departure_kind = d + timedelta(days=r.randint(0, 3)), "sale"
            a.buyer_pic = proc["pic"] if r.random() < 0.8 else r.choice(["QSYD0001", "NSYD0012", "3SYD0007"])

    def records(self) -> None:
        """Emit AgriWebb-shaped records for each animal."""
        p0, p1 = settings.period_start, settings.period_end
        bounds = [p0, date(2025, 10, 1), date(2026, 1, 1), date(2026, 4, 1), p1]
        for a in self.animals:
            end = a.departure or p1
            if a.arrival_kind in ("birth", "purchase"):
                a.records.append(self._rec(a, "birthing" if a.arrival_kind == "birth" else "purchase", a.arrival))
                a.records.append(self._weigh(a, a.arrival, "Check"))
            for b in bounds:
                if a.arrival <= b <= end and not (a.departure_kind == "death" and b == end):
                    a.records.append(self._weigh(a, b, "Check"))
            if a.departure_kind == "sale":
                a.records.append(self._weigh(a, a.departure, "Sale"))
                a.records.append(
                    self._rec(
                        a,
                        "sale",
                        a.departure,
                        departureDate=_ms(a.departure),
                        newOwnerName=a.buyer_pic,
                        reference=f"NVD-{self.rng.randrange(10**7, 10**8)}",
                    )
                )
            elif a.departure_kind == "death":
                a.records.append(self._rec(a, "death", a.departure))

    def _rec(self, a: Animal, kind: str, d: date, **extra) -> dict:
        return {
            "recordId": self._uid(),
            "recordType": kind,
            "observationDate": _ms(d),
            "animalId": a.animal_id,
            **extra,
        }

    def _weigh(self, a: Animal, d: date, event: str) -> dict:
        w = round(self.weight(a, d) * self.rng.gauss(1.0, 0.015), 1)
        return self._rec(
            a, "weigh", d, recordInputType="Individual", weight={"value": w, "unit": "kg"}, weighEvent=event
        )


def _growth_curve(rng: random.Random, adg: tuple[float, ...]) -> list[float]:
    days = (date(2026, 7, 2) - EPOCH).days
    q = {7: 0, 8: 0, 9: 0, 10: 1, 11: 1, 12: 1, 1: 2, 2: 2, 3: 2, 4: 3, 5: 3, 6: 3}
    year_factor = {y: rng.uniform(0.85, 1.15) for y in range(2016, 2027)}
    daily = [adg[q[(EPOCH + timedelta(i)).month]] * year_factor[(EPOCH + timedelta(i)).year] for i in range(days)]
    return [0.0, *accumulate(daily)]


def _pic(rng: random.Random, state: str) -> str:
    letters = "ABCDEFGHJKLMNPQRSTUVWXYZ"
    tail = "".join(rng.choice(letters) for _ in range(3)) + f"{rng.randrange(1000, 9999)}"
    return {"QLD": "Q", "NSW": "N", "VIC": "3", "NT": "T"}[state] + tail


def _farms(rng: random.Random) -> list[dict]:
    names = rng.sample([f"{p} {s}" for p in PREFIX for s in SUFFIX], 56)
    names[0] = "Kurrajong Downs"
    farms = []
    for i in range(56):
        region = REGIONS[i % len(REGIONS)]
        z = ZONE[region.zone]
        farms.append(
            dict(
                farmId=f"F{i + 1:03d}",
                name=names[i],
                region=region.code,
                state=region.state,
                pic=_pic(rng, region.state),
                agriwebbFarmId=str(uuid.UUID(int=rng.getrandbits(128), version=4)),
                cows=rng.randint(*z["cows"]),
                # Extensive country north of Capricorn: lower weaning, higher losses, slower growth.
                weaning=round(rng.uniform(*(NORTH["weaning"] if region.north_of_capricorn else z["weaning"])), 3),
                mortality=round(rng.uniform(*(NORTH["mortality"] if region.north_of_capricorn else z["mortality"])), 4),
                growth=NORTH["growth"] if region.north_of_capricorn else 1.0,
                trader=rng.random() < 0.3,
                lat=round(region.lat + rng.uniform(-1.2, 1.2), 3),
                lon=round(region.lon + rng.uniform(-1.5, 1.5), 3),
                quality=rng.choices(["clean", "minor", "major"], [0.62, 0.26, 0.12])[0],
            )
        )
    farms[0].update(cows=210, weaning=0.70, trader=False, quality="clean")
    return farms


def _inject_mismatches(rng: random.Random, sim: FarmSim, movements: list[dict]) -> list[dict]:
    """Make herd records and NLIS disagree the way real books do."""
    q = sim.farm["quality"]
    if q == "clean":
        return movements
    drop, phantom, unrecorded = {"minor": (0.04, 0.02, 0.0), "major": (0.2, 0.08, 0.04)}[q]
    off = [m for m in movements if m["fromPic"] == sim.farm["pic"]]
    dropped = {id(m) for m in rng.sample(off, int(len(off) * drop))}
    movements = [m for m in movements if id(m) not in dropped]
    for m in rng.sample(movements, len(movements) // 10):
        m["movementDate"] = (date.fromisoformat(m["movementDate"]) + timedelta(days=rng.randint(8, 25))).isoformat()
    alive = [a for a in sim.animals if a.departure is None and a.arrival_kind != "birth"]
    for a in rng.sample(alive, int(len(alive) * phantom)):
        d = settings.period_start + timedelta(days=rng.randint(30, 300))
        movements.append(_movement(rng, a, sim.farm["pic"], rng.choice(["QSYD0001", "NSYD0012"]), d))
        a.records = [r for r in a.records if r["observationDate"] <= _ms(d)]
    sold = [a for a in sim.animals if a.departure_kind == "sale"]
    for a in rng.sample(sold, int(len(sold) * unrecorded)):
        a.records = [r for r in a.records if r["recordType"] != "sale"]
    return movements


def _movement(rng: random.Random, a: Animal, src: str, dst: str, d: date) -> dict:
    kind = (
        "PROPERTY_TO_PROCESSOR"
        if dst in {p["pic"] for p in PROCESSORS}
        else ("PROPERTY_TO_SALEYARD" if "SYD" in dst else "PROPERTY_TO_PROPERTY")
    )
    return {
        "transactionId": f"T{rng.randrange(10**9, 10**10)}",
        "nlisId": a.nlis_id,
        "rfid": a.eid,
        "species": "Cattle",
        "fromPic": src,
        "toPic": dst,
        "movementDate": d.isoformat(),
        "nvdNumber": f"{rng.randrange(10**7, 10**8)}",
        "movementType": kind,
    }


def _animal_payload(sim: FarmSim, a: Animal) -> dict:
    fate = {"sale": "Sold", "death": "Dead"}.get(a.departure_kind or "", "Alive")
    return {
        "animalId": a.animal_id,
        "farmId": sim.farm["agriwebbFarmId"],
        "identity": {
            "eid": a.eid,
            "vid": f"{a.birth.year % 100:02d}-{sim.serial % 997:03d}",
            "tags": [{"type": "NLIS", "value": a.nlis_id}],
        },
        "characteristics": {
            "birthDate": _ms(a.birth),
            "birthYear": a.birth.year,
            "sex": a.sex,
            "breedAssessed": sim.farm["breed"],
            "speciesCommonName": "Cattle",
        },
        "state": {
            "fate": fate,
            "onFarm": fate == "Alive",
            "onFarmDate": _ms(a.arrival),
            "offFarmDate": _ms(a.departure) if a.departure and fate != "Alive" else None,
            "fertilityStatus": "Neutered" if a.steer else "Fertile",
        },
        "purchasedFrom": a.vendor_pic,
        "purchaseLocationId": a.vendor_pic,
        "records": sorted(a.records, key=lambda r: r["observationDate"]),
    }


def _fields(rng: random.Random, sim: FarmSim, area: float, coverage: float) -> list[dict]:
    n = rng.randint(6, 18)
    cuts = sorted(rng.random() for _ in range(n - 1))
    parts = [b - a for a, b in zip([0, *cuts], [*cuts, 1], strict=True)]
    return [
        {
            "id": sim._uid(),
            "name": f"{rng.choice(['North', 'South', 'River', 'Creek', 'Top', 'Bottom', 'Laneway', 'Back'])} {k + 1}",
            "farmId": sim.farm["agriwebbFarmId"],
            "totalArea": round(area * coverage * p, 1),
            "grazableArea": round(area * coverage * p * rng.uniform(0.85, 0.97), 1),
            "unit": "ha",
            "landUse": "GRAZING",
        }
        for k, p in enumerate(parts)
    ]


def _satellite(
    rng: random.Random, farm: dict, region: Region, area: float, herd_ae: float, clearing: tuple | None
) -> dict:
    z = ZONE[region.zone]
    target = herd_ae * rng.uniform(1.0, 1.35) * (0.6 if farm["quality"] == "major" else 1.0)
    mean_tsdm = target * 8 * 365 / (area * 0.9 * 3.0 * 0.3)
    shape = [t / (sum(z["tsdm"]) / 4) for t in z["tsdm"]]
    pasture = []
    for m in range(12):
        d = date(2025 + (m + 6) // 12, (m + 6) % 12 + 1, 15)
        k = m // 3
        pasture.append(
            {
                "date": d.isoformat(),
                "tsdmKgHa": round(mean_tsdm * shape[k] * rng.uniform(0.9, 1.1)),
                "groundCoverPct": round(min(99, z["cover"][k] * rng.uniform(0.95, 1.05)), 1),
            }
        )
    base = area * rng.uniform(*z["woody"])
    woody = []
    for y in range(2018, 2026):
        ha = base * rng.uniform(0.993, 1.007)
        if clearing and y >= clearing[0]:
            ha -= clearing[1]
        woody.append({"date": f"{y}-12-31", "areaHa": round(ha, 1), "pct": round(100 * ha / area, 2)})
    if farm.get("cloud_gaps"):
        woody = [w for w in woody if w["date"][:4] in ("2018", "2019", "2020", "2025")]
    return {
        "propertyId": farm["pic"],
        "provider": "synthetic (Cibo Labs-like)",
        "boundary": {"areaHa": round(area, 1)},
        "pasture": pasture,
        "woodyCover": woody,
    }


def _consents(rng: random.Random, farms: list[dict], loans: list[dict]) -> tuple[list, list]:
    connections, consents = [], []
    granted = "2026-0{}-{:02d}T09:00:00+10:00"
    lender_of = {}
    for loan in loans:
        lender_of.setdefault(loan["farmId"], []).append(loan["lenderId"])
    for f in farms:
        if not f["connected"]:
            continue
        ts = granted.format(rng.randint(3, 9), rng.randint(1, 28))
        connections.append(
            {"farmId": f["farmId"], "source": "agriwebb", "authType": "oauth2_authorization_code", "connectedAt": ts}
        )
        connections.append(
            {"farmId": f["farmId"], "source": "satellite", "authType": "licensed_boundary", "connectedAt": ts}
        )
        if f["nlis_linked"]:
            connections.append(
                {"farmId": f["farmId"], "source": "nlis", "authType": "isc_pic_authorisation", "connectedAt": ts}
            )
        purposes = []
        if f["farmId"] == HERO_FARM or rng.random() < 0.78:
            purposes.append("regional_benchmark")
        if f["farmId"] != HERO_FARM and rng.random() < 0.7:
            purposes.append("processor_cohort")
        for lender in lender_of.get(f["farmId"], []):
            if f["farmId"] != HERO_FARM and rng.random() < 0.75:
                purposes.append(f"lender_share:{lender}")
        for p in purposes:
            consents.append(
                {
                    "consentId": f"C-{f['farmId']}-{p.replace(':', '-')}",
                    "farmId": f["farmId"],
                    "purpose": p,
                    "scopes": ["footprint", "reconciliation", "deforestation"]
                    if p.startswith("lender")
                    else ["footprint"],
                    "grantedAt": ts,
                    "revokedAt": None,
                    "basis": "Australian Farm Data Code v2",
                }
            )
    return connections, consents


def generate(out: Path | None = None) -> Path:
    """Generate all fixtures deterministically; returns the fixtures directory."""
    out = out or settings.fixtures_dir
    rng = random.Random(settings.seed)
    farms = _farms(rng)
    regions = {r.code: r for r in REGIONS}
    curves = {z: _growth_curve(rng, ZONE[z]["adg"]) for z in ZONE}
    clearing = {"F009": (2023, 0.06), "F012": (2022, 0.04), "F013": (2019, 0.05)}
    for f in farms:
        f["connected"] = f["farmId"] in (HERO_FARM, *clearing) or rng.random() < 0.8
        f["nlis_linked"] = f["connected"] and (f["farmId"] == HERO_FARM or rng.random() < 0.88)
        f["breed"] = rng.choice(BREEDS[regions[f["region"]].zone])
    farms[20]["cloud_gaps"] = True

    for sub in ("agriwebb", "nlis", "satellite", "herdproof"):
        (out / sub).mkdir(parents=True, exist_ok=True)
    inputs, loans = [], []
    for f in farms:
        region = regions[f["region"]]
        sim = FarmSim(rng, f, region, curves[region.zone])
        sim.run()
        sim.records()
        movements = []
        for a in sim.animals:
            if a.departure_kind == "sale":
                movements.append(
                    _movement(rng, a, f["pic"], a.buyer_pic, a.departure + timedelta(days=rng.randint(0, 2)))
                )
            if a.arrival_kind == "purchase":
                movements.append(_movement(rng, a, a.vendor_pic, f["pic"], a.arrival))
        movements = _inject_mismatches(rng, sim, movements)
        head = len([a for a in sim.animals if a.arrival_kind == "opening"])
        area = head * rng.uniform(*region.ha_per_ae)
        coverage = rng.uniform(0.66, 0.74) if f["quality"] == "major" else rng.uniform(0.95, 1.0)
        cl = clearing.get(f["farmId"])
        sat = _satellite(rng, f, region, area, head * 0.95, (cl[0], area * cl[1]) if cl else None)
        aw = {
            "farms": {
                "data": {
                    "farms": [
                        {
                            "id": f["agriwebbFarmId"],
                            "name": f["name"],
                            "identifiers": [{"type": "PIC", "value": f["pic"]}],
                        }
                    ]
                }
            },
            "fields": {"data": {"fields": _fields(rng, sim, area, coverage)}},
            "animals": {
                "data": {
                    "animals": {
                        "nonPagedCount": len(sim.animals),
                        "animals": [_animal_payload(sim, a) for a in sim.animals],
                    }
                }
            },
        }
        _dump(out / "agriwebb" / f"{f['agriwebbFarmId']}.json", aw)
        _dump(
            out / "nlis" / f"{f['pic']}.json",
            {
                "pic": f["pic"],
                "fromDate": settings.period_start.isoformat(),
                "toDate": settings.period_end.isoformat(),
                "movements": movements,
            },
        )
        _dump(out / "satellite" / f"{f['pic']}.json", sat)
        sold_kg = sum(sim.weight(a, a.departure) for a in sim.animals if a.departure_kind == "sale")
        temperate = region.zone == "temperate"
        inputs.append(
            {
                "farmId": f["farmId"],
                "dieselL": round(head * rng.uniform(3, 8)),
                "petrolL": round(head * rng.uniform(0.4, 1.4)),
                "electricityKwh": round(rng.uniform(2500, 16000)),
                "renewableFraction": rng.choice([0, 0, 0, 0.3, 1.0]),
                "fertiliserNKg": round(area * rng.uniform(0, 18)) if temperate and rng.random() < 0.6 else 0,
                "ureaKg": round(area * rng.uniform(0, 8)) if temperate and rng.random() < 0.4 else 0,
                "limeT": round(area * rng.uniform(0, 0.15), 1) if temperate and rng.random() < 0.3 else 0,
                "plantingsHa": round(rng.uniform(5, 40), 1) if rng.random() < 0.3 else 0,
            }
        )
        assets = area * region.land_value_ha * rng.uniform(0.85, 1.2) + head * 1500
        f.update(
            area_ha=round(area, 1),
            revenue_aud=round(sold_kg * ZONE[region.zone]["price"]),
            assets_aud=round(assets, -3),
            head=head,
        )
    inputs[0].update(renewableFraction=0, plantingsHa=0, fertiliserNKg=0)

    for lender in LENDERS:
        pool = [f for f in farms if f["state"] in lender["states"]]
        book = [farms[0]] if lender["lenderId"] == "L1" else []
        lent = {loan["farmId"] for loan in loans}
        book += rng.sample(
            [f for f in pool if f not in book and f["farmId"] not in lent], 24 if lender["lenderId"] == "L1" else 18
        )
        for f in book:
            has_rev = lender["lenderId"] == "L1" or rng.random() < 0.6
            loans.append(
                {
                    "lenderId": lender["lenderId"],
                    "farmId": f["farmId"],
                    "facilityId": f"{lender['lenderId']}-{rng.randrange(10**5, 10**6)}",
                    "outstandingAud": round(f["assets_aud"] * rng.uniform(0.18, 0.42), -3),
                    "totalAssetsAud": f["assets_aud"],
                    "revenueAud": f["revenue_aud"] if has_rev else None,
                    "declaredHead": f["head"] if (lender["lenderId"] == "L2" and rng.random() < 0.35) else None,
                }
            )
    for c in clearing:  # make sure the clearing farms are in a lender book for the story
        if c not in {loan["farmId"] for loan in loans}:
            f = next(x for x in farms if x["farmId"] == c)
            loans.append(
                {
                    "lenderId": "L1" if f["state"] != "VIC" else "L2",
                    "farmId": c,
                    "facilityId": f"X-{c}",
                    "outstandingAud": round(f["assets_aud"] * 0.3, -3),
                    "totalAssetsAud": f["assets_aud"],
                    "revenueAud": f["revenue_aud"],
                    "declaredHead": None,
                }
            )
    connections, consents = _consents(rng, farms, loans)
    registry = [
        {k: f[k] for k in ("farmId", "name", "region", "state", "pic", "agriwebbFarmId", "lat", "lon", "breed")}
        for f in farms
    ]
    hp = out / "herdproof"
    _dump(hp / "farms.json", registry)
    _dump(hp / "regions.json", [r.__dict__ for r in REGIONS])
    _dump(hp / "farm_inputs.json", inputs)
    _dump(hp / "lenders.json", LENDERS)
    _dump(hp / "loans.json", loans)
    _dump(hp / "processors.json", PROCESSORS)
    _dump(hp / "connections.json", connections)
    _dump(hp / "consents.json", consents)
    return out


def _dump(path: Path, obj) -> None:
    path.write_text(json.dumps(obj, separators=(",", ":")), encoding="utf-8")
