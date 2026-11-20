"""AgriWebb GraphQL adapter (https://api.agriwebb.com/v2). Marketplace partners authenticate via OAuth2."""

from herdproof.adapters.base import FarmRef, Rows, SourceAdapter, ms_to_date

FIELDS_QUERY = """
query Fields($farmId: String!) {
  fields(farmId: $farmId) { id name totalArea grazableArea unit landUse }
}"""

ANIMALS_QUERY = """
query Animals($farmId: String!, $limit: Int, $skip: Int) {
  animals(farmId: $farmId, limit: $limit, skip: $skip) {
    nonPagedCount
    animals {
      animalId
      identity { eid vid tags { type value } }
      characteristics { birthDate sex breedAssessed speciesCommonName }
      state { fate onFarm onFarmDate offFarmDate fertilityStatus }
      purchaseLocationId
      records {
        recordId recordType observationDate
        ... on WeighRecord { weight { value unit } weighEvent }
        ... on SaleRecord { departureDate newOwnerName reference }
      }
    }
  }
}"""

PAGE = 500


class AgriWebbAdapter(SourceAdapter):
    source = "agriwebb"
    schema = {
        "agriwebb_animals": {
            "farm_id": "VARCHAR",
            "animal_id": "VARCHAR",
            "eid": "VARCHAR",
            "nlis_id": "VARCHAR",
            "species": "VARCHAR",
            "sex": "VARCHAR",
            "birth_date": "DATE",
            "breed": "VARCHAR",
            "fertility_status": "VARCHAR",
            "fate": "VARCHAR",
            "on_farm_date": "DATE",
            "off_farm_date": "DATE",
            "purchase_location_id": "VARCHAR",
        },
        "agriwebb_records": {
            "farm_id": "VARCHAR",
            "record_id": "VARCHAR",
            "animal_id": "VARCHAR",
            "record_type": "VARCHAR",
            "observation_date": "DATE",
            "weight_kg": "DOUBLE",
            "weigh_event": "VARCHAR",
            "new_owner": "VARCHAR",
        },
        "agriwebb_fields": {
            "farm_id": "VARCHAR",
            "field_id": "VARCHAR",
            "name": "VARCHAR",
            "total_area_ha": "DOUBLE",
            "grazable_area_ha": "DOUBLE",
            "land_use": "VARCHAR",
        },
    }

    def extract(self, farm: FarmRef) -> dict[str, Rows]:
        fields = self.transport(farm.agriwebb_farm_id, "fields", query=FIELDS_QUERY, farmId=farm.agriwebb_farm_id)
        animals = self._animals(farm)
        return {
            "agriwebb_fields": [
                {
                    "farm_id": farm.farm_id,
                    "field_id": f["id"],
                    "name": f["name"],
                    "total_area_ha": f["totalArea"],
                    "grazable_area_ha": f["grazableArea"],
                    "land_use": f["landUse"],
                }
                for f in fields["data"]["fields"]
            ],
            "agriwebb_animals": [self._animal_row(farm, a) for a in animals],
            "agriwebb_records": [self._record_row(farm, r) for a in animals for r in a["records"]],
        }

    def _animals(self, farm: FarmRef) -> list[dict]:
        out, skip, total = [], 0, None
        while total is None or skip < total:
            page = self.transport(
                farm.agriwebb_farm_id,
                "animals",
                query=ANIMALS_QUERY,
                farmId=farm.agriwebb_farm_id,
                limit=PAGE,
                skip=skip,
            )["data"]["animals"]
            total, batch = page["nonPagedCount"], page["animals"]
            out += batch
            skip += len(batch)
            if not batch:
                break
        return out

    @staticmethod
    def _animal_row(farm: FarmRef, a: dict) -> dict:
        ident, ch, st = a["identity"], a["characteristics"], a["state"]
        nlis = next((t["value"] for t in ident.get("tags") or [] if t["type"] == "NLIS"), None)
        return {
            "farm_id": farm.farm_id,
            "animal_id": a["animalId"],
            "eid": ident.get("eid"),
            "nlis_id": nlis,
            "species": ch.get("speciesCommonName"),
            "sex": ch.get("sex"),
            "birth_date": ms_to_date(ch.get("birthDate")),
            "breed": ch.get("breedAssessed"),
            "fertility_status": st.get("fertilityStatus"),
            "fate": st.get("fate"),
            "on_farm_date": ms_to_date(st.get("onFarmDate")),
            "off_farm_date": ms_to_date(st.get("offFarmDate")),
            "purchase_location_id": a.get("purchaseLocationId"),
        }

    @staticmethod
    def _record_row(farm: FarmRef, r: dict) -> dict:
        weight = r.get("weight") or {}
        kg = weight.get("value") if weight.get("unit", "kg") == "kg" else None
        return {
            "farm_id": farm.farm_id,
            "record_id": r["recordId"],
            "animal_id": r["animalId"],
            "record_type": r["recordType"],
            "observation_date": ms_to_date(r["observationDate"]),
            "weight_kg": kg,
            "weigh_event": r.get("weighEvent"),
            "new_owner": r.get("newOwnerName"),
        }
