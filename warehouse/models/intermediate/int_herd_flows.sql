-- Herd book flows for the period and liveweight produced = sold - purchased + closing - opening.
{% set p_start = "cast('" ~ var('period_start') ~ "' as date)" %}
{% set p_end = "cast('" ~ var('period_end') ~ "' as date)" %}
with animals as (
    select * from {{ ref('stg_agriwebb__animals') }}
),

records as (
    select * from {{ ref('stg_agriwebb__records') }}
    where observation_date between {{ p_start }} and {{ p_end }}
),

events as (
    select farm_id, animal_id, record_type, observation_date
    from records
    where record_type in ('birthing', 'purchase', 'sale', 'death')
),

event_weights as (
    select e.farm_id, e.record_type, w.weight_kg
    from events e
    join {{ ref('int_animal_weights') }} w
      on w.animal_id = e.animal_id
     and case when e.record_type = 'purchase' then w.observation_date >= e.observation_date
              else w.observation_date <= e.observation_date end
    where e.record_type in ('purchase', 'sale')
    qualify row_number() over (
        partition by e.animal_id, e.record_type
        order by case when e.record_type = 'purchase' then w.observation_date end asc,
                 case when e.record_type = 'sale' then w.observation_date end desc
    ) = 1
),

inventory as (
    select
        a.farm_id, a.animal_id,
        a.on_farm_date <= {{ p_start }} and (a.off_farm_date is null or a.off_farm_date > {{ p_start }}) as is_opening,
        a.on_farm_date <= {{ p_end }} and (a.off_farm_date is null or a.off_farm_date > {{ p_end }}) as is_closing
    from animals a
),

inventory_weights as (
    select
        i.farm_id,
        sum(case when i.is_opening then 1 else 0 end) as opening_head,
        sum(case when i.is_closing then 1 else 0 end) as closing_head,
        sum(case when i.is_opening then ow.weight_kg else 0 end) as opening_lw_kg,
        sum(case when i.is_closing then cw.weight_kg else 0 end) as closing_lw_kg
    from inventory i
    left join (
        select animal_id, weight_kg from {{ ref('int_animal_weights') }}
        where observation_date <= {{ p_start }}
        qualify row_number() over (partition by animal_id order by observation_date desc) = 1
    ) ow using (animal_id)
    left join (
        select animal_id, weight_kg from {{ ref('int_animal_weights') }}
        where observation_date <= {{ p_end }}
        qualify row_number() over (partition by animal_id order by observation_date desc) = 1
    ) cw using (animal_id)
    group by i.farm_id
),

counts as (
    select
        farm_id,
        count(distinct case when record_type = 'birthing' then animal_id end) as births,
        count(distinct case when record_type = 'purchase' then animal_id end) as purchases,
        count(distinct case when record_type = 'sale' then animal_id end) as sales,
        count(distinct case when record_type = 'death' then animal_id end) as deaths
    from events
    group by farm_id
),

flow_weights as (
    select
        farm_id,
        sum(case when record_type = 'sale' then weight_kg else 0 end) as sold_lw_kg,
        sum(case when record_type = 'purchase' then weight_kg else 0 end) as purchased_lw_kg
    from event_weights
    group by farm_id
)

select
    iw.farm_id,
    iw.opening_head,
    coalesce(c.births, 0) as births,
    coalesce(c.purchases, 0) as purchases,
    coalesce(c.sales, 0) as sales,
    coalesce(c.deaths, 0) as deaths,
    iw.closing_head,
    iw.opening_head + coalesce(c.births, 0) + coalesce(c.purchases, 0)
        - coalesce(c.sales, 0) - coalesce(c.deaths, 0) as expected_closing_head,
    iw.opening_lw_kg,
    iw.closing_lw_kg,
    coalesce(fw.sold_lw_kg, 0) as sold_lw_kg,
    coalesce(fw.purchased_lw_kg, 0) as purchased_lw_kg,
    coalesce(fw.sold_lw_kg, 0) - coalesce(fw.purchased_lw_kg, 0)
        + iw.closing_lw_kg - iw.opening_lw_kg as lw_produced_kg
from inventory_weights iw
left join counts c using (farm_id)
left join flow_weights fw using (farm_id)
