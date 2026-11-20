"""Satellite pasture and woody-cover adapter, queried by property boundary.

Production: a licensed provider (e.g. Cibo Labs, no public API verified) or Digital Earth Australia Sentinel-2 public data.
"""

from herdproof.adapters.base import FarmRef, Rows, SourceAdapter


class SatelliteAdapter(SourceAdapter):
    source = "satellite"
    schema = {
        "satellite_boundary": {"farm_id": "VARCHAR", "provider": "VARCHAR", "boundary_area_ha": "DOUBLE"},
        "satellite_pasture": {
            "farm_id": "VARCHAR",
            "obs_date": "DATE",
            "tsdm_kg_ha": "DOUBLE",
            "ground_cover_pct": "DOUBLE",
        },
        "satellite_woody": {"farm_id": "VARCHAR", "obs_date": "DATE", "woody_area_ha": "DOUBLE", "woody_pct": "DOUBLE"},
    }

    def extract(self, farm: FarmRef) -> dict[str, Rows]:
        p = self.transport(farm.pic, pic=farm.pic)
        return {
            "satellite_boundary": [
                {"farm_id": farm.farm_id, "provider": p["provider"], "boundary_area_ha": p["boundary"]["areaHa"]}
            ],
            "satellite_pasture": [
                {
                    "farm_id": farm.farm_id,
                    "obs_date": o["date"],
                    "tsdm_kg_ha": o["tsdmKgHa"],
                    "ground_cover_pct": o["groundCoverPct"],
                }
                for o in p["pasture"]
            ],
            "satellite_woody": [
                {"farm_id": farm.farm_id, "obs_date": o["date"], "woody_area_ha": o["areaHa"], "woody_pct": o["pct"]}
                for o in p["woodyCover"]
            ],
        }
