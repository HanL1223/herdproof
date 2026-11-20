"""ISC NLIS adapter: PIC-scoped livestock movements (licensed API, accessed with the grazier's PIC authorisation)."""

from herdproof.adapters.base import FarmRef, Rows, SourceAdapter


class NlisAdapter(SourceAdapter):
    source = "nlis"
    schema = {
        "nlis_movements": {
            "farm_id": "VARCHAR",
            "transaction_id": "VARCHAR",
            "nlis_id": "VARCHAR",
            "rfid": "VARCHAR",
            "species": "VARCHAR",
            "from_pic": "VARCHAR",
            "to_pic": "VARCHAR",
            "movement_date": "DATE",
            "nvd_number": "VARCHAR",
            "movement_type": "VARCHAR",
        }
    }

    def extract(self, farm: FarmRef) -> dict[str, Rows]:
        payload = self.transport(farm.pic, pic=farm.pic)
        return {
            "nlis_movements": [
                {
                    "farm_id": farm.farm_id,
                    "transaction_id": m["transactionId"],
                    "nlis_id": m["nlisId"],
                    "rfid": m["rfid"],
                    "species": m["species"],
                    "from_pic": m["fromPic"],
                    "to_pic": m["toPic"],
                    "movement_date": m["movementDate"],
                    "nvd_number": m["nvdNumber"],
                    "movement_type": m["movementType"],
                }
                for m in payload["movements"]
            ]
        }
