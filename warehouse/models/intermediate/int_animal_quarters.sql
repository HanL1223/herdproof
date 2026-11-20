-- One row per animal per quarter on farm, with GAF class and as-of liveweights at entry and exit.
with quarters as (
    select *, {{ dbt.datediff('start_date', 'end_date', 'day') }} as quarter_days
    from {{ ref('int_reporting_quarters') }}
),

spans as (
    select
        a.farm_id, a.animal_id, a.sex, a.is_steer, a.birth_date,
        q.quarter, q.quarter_days,
        greatest(a.on_farm_date, q.start_date) as entry_date,
        least(coalesce(a.off_farm_date, q.end_date), q.end_date) as exit_date
    from {{ ref('stg_agriwebb__animals') }} a
    cross join quarters q
    where a.on_farm_date < q.end_date
      and (a.off_farm_date is null or a.off_farm_date > q.start_date)
),

start_weight as (
    select s.animal_id, s.quarter, w.weight_kg
    from spans s
    join {{ ref('int_animal_weights') }} w on w.animal_id = s.animal_id and w.observation_date <= s.entry_date
    qualify row_number() over (partition by s.animal_id, s.quarter order by w.observation_date desc) = 1
),

end_weight as (
    select s.animal_id, s.quarter, w.weight_kg, w.observation_date >= s.entry_date as weighed_in_span
    from spans s
    join {{ ref('int_animal_weights') }} w on w.animal_id = s.animal_id and w.observation_date <= s.exit_date
    qualify row_number() over (partition by s.animal_id, s.quarter order by w.observation_date desc) = 1
),

measured as (
    select
        s.*,
        {{ dbt.datediff('s.entry_date', 's.exit_date', 'day') }} as span_days,
        {{ dbt.datediff('s.birth_date', 's.entry_date', 'day') }} as age_days,
        coalesce(sw.weight_kg, ew.weight_kg) as start_kg,
        coalesce(ew.weight_kg, sw.weight_kg) as end_kg,
        coalesce(ew.weighed_in_span, false) as weighed_in_span
    from spans s
    left join start_weight sw using (animal_id, quarter)
    left join end_weight ew using (animal_id, quarter)
)

select
    *,
    (start_kg + end_kg) / 2 as avg_kg,
    least(2.0, greatest(-1.0, (end_kg - start_kg) / nullif(span_days, 0))) as adg_kg,
    case
        when age_days < 200 then 'calves'
        when is_steer or sex = 'Male' and age_days < 365 then
            case when age_days < 365 then 'steersLt1' when age_days < 730 then 'steers1To2' else 'steersGt2' end
        when sex = 'Male' then 'bullsGt1'
        when age_days < 365 then 'heifersLt1'
        when age_days < 730 then 'heifers1To2'
        else 'cowsGt2'
    end as gaf_class
from measured
where span_days > 0
