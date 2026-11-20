-- GAF-style input grain: farm x quarter x class with average head, liveweight and daily gain.
with agg as (
    select
        farm_id, quarter, gaf_class,
        max(quarter_days) as quarter_days,
        sum(span_days) as head_days,
        sum(avg_kg * span_days) / sum(span_days) as liveweight_kg,
        sum(adg_kg * span_days) / sum(span_days) as liveweight_gain_kg_day,
        sum(span_days * power(avg_kg / {{ ef('ae_reference_lw') }}, 0.75)) / 365.0 as ae_years,
        sum(case when weighed_in_span then span_days else 0 end) as evidenced_days
    from {{ ref('int_animal_quarters') }}
    group by farm_id, quarter, gaf_class
),

nursing as (
    select
        farm_id, quarter,
        least(1.0, sum(case when gaf_class = 'calves' then head_days else 0 end)
              / nullif(sum(case when gaf_class = 'cowsGt2' then head_days else 0 end), 0)) as nursing_fraction
    from agg
    group by farm_id, quarter
)

select
    a.*,
    a.head_days / a.quarter_days as head,
    coalesce(n.nursing_fraction, 0) as nursing_fraction
from agg a
left join nursing n using (farm_id, quarter)
