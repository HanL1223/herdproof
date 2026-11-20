select
    f.farm_id,
    f.name as farm_name,
    f.pic,
    f.agriwebb_farm_id,
    f.region as region_code,
    r.name as region_name,
    f.state,
    r.zone,
    r.north_of_capricorn,
    r.rainfall_above_600,
    f.breed,
    f.lat,
    f.lon
from {{ source('raw', 'hp_farms') }} f
join {{ source('raw', 'hp_regions') }} r on r.code = f.region
