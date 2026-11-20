select
    farm_id,
    max(case when source = 'agriwebb' then 1 else 0 end) = 1 as has_agriwebb,
    max(case when source = 'nlis' then 1 else 0 end) = 1 as has_nlis,
    max(case when source = 'satellite' then 1 else 0 end) = 1 as has_satellite,
    min(connected_at) as first_connected_at
from {{ source('raw', 'hp_connections') }}
group by farm_id
