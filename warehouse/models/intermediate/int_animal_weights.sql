select farm_id, animal_id, observation_date, max(weight_kg) as weight_kg
from {{ ref('stg_agriwebb__records') }}
where record_type = 'weigh' and weight_kg > 0
group by farm_id, animal_id, observation_date
