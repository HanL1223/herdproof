-- Sale events with buyer and as-of sale liveweight.
select r.farm_id, r.animal_id, r.observation_date as sale_date, r.new_owner as buyer_pic, w.weight_kg as sale_weight_kg
from {{ ref('stg_agriwebb__records') }} r
left join {{ ref('int_animal_weights') }} w on w.animal_id = r.animal_id and w.observation_date <= r.observation_date
where r.record_type = 'sale'
  and r.observation_date between cast('{{ var("period_start") }}' as date) and cast('{{ var("period_end") }}' as date)
qualify row_number() over (partition by r.animal_id order by w.observation_date desc) = 1
