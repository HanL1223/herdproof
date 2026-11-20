select
    farm_id,
    record_id,
    animal_id,
    record_type,
    observation_date,
    weight_kg,
    weigh_event,
    new_owner
from {{ source('raw', 'agriwebb_records') }}
