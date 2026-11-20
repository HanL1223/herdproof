select
    farm_id,
    animal_id,
    eid as rfid,
    nlis_id,
    sex,
    fertility_status = 'Neutered' as is_steer,
    birth_date,
    breed,
    fate,
    on_farm_date,
    case when fate in ('Sold', 'Dead') then off_farm_date end as off_farm_date,
    purchase_location_id
from {{ source('raw', 'agriwebb_animals') }}
where species = 'Cattle'
