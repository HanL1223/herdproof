-- De-identified supplier cohorts: consented farms only, suppressed below k farms.
with supply as (
    select s.farm_id, p.processor_id, count(*) as head_supplied, sum(s.sale_weight_kg) as lw_supplied_kg
    from {{ ref('int_animal_sales') }} s
    join {{ ref('stg_hp__processors') }} p on p.processor_pic = s.buyer_pic
    group by s.farm_id, p.processor_id
),

cohort as (
    select
        s.*, f.state, f.zone,
        fp.intensity_kg_per_kg_lw,
        case when f.zone = 'tropical' then tp.value else tm.value end as proxy_intensity,
        r.confidence,
        d.status as deforestation_status
    from supply s
    join {{ ref('stg_hp__farms') }} f using (farm_id)
    join {{ ref('fct_farm_footprint') }} fp using (farm_id)
    join {{ ref('fct_reconciliation') }} r using (farm_id)
    left join {{ ref('fct_deforestation') }} d using (farm_id)
    join {{ ref('ref_pcaf_proxies') }} tp on tp.proxy = 'carcase' and tp.zone = 'tropical'
    join {{ ref('ref_pcaf_proxies') }} tm on tm.proxy = 'carcase' and tm.zone = 'temperate'
    where s.farm_id in (select farm_id from {{ ref('stg_app__consents') }} where purpose = 'processor_cohort')
),

segments as (
    select processor_id, 'All suppliers' as segment, * exclude (processor_id) from cohort
    union all
    select processor_id, state as segment, * exclude (processor_id) from cohort
),

agg as (
    select
        processor_id,
        segment,
        count(*) as n_farms,
        sum(head_supplied) as head_supplied,
        sum(lw_supplied_kg) / 1000 as lw_supplied_t,
        sum(intensity_kg_per_kg_lw * lw_supplied_kg) / sum(lw_supplied_kg) as primary_intensity,
        sum(proxy_intensity * lw_supplied_kg) / sum(lw_supplied_kg) as proxy_intensity,
        percentile_cont(0.25) within group (order by intensity_kg_per_kg_lw) as p25_intensity,
        percentile_cont(0.75) within group (order by intensity_kg_per_kg_lw) as p75_intensity,
        avg(confidence) as avg_confidence,
        sum(case when deforestation_status = 'clear' then lw_supplied_kg else 0 end) / sum(lw_supplied_kg) as clear_share,
        sum(case when deforestation_status = 'review' then 1 else 0 end) as n_review
    from segments
    group by processor_id, segment
),

-- Complementary suppression: state segments publish only if every sibling meets k; otherwise only "All".
flags as (
    select
        *,
        case
            when segment = 'All suppliers' then n_farms >= {{ var('cohort_min_farms') }}
            else min(n_farms) over (partition by processor_id, segment = 'All suppliers') >= {{ var('cohort_min_farms') }}
        end as is_published
    from agg
)

select
    processor_id,
    segment,
    n_farms,
    is_published,
    -- Totals only at "All" level so sibling segments cannot be differenced; spreads need n >= 10.
    case when is_published and segment = 'All suppliers' then head_supplied end as head_supplied,
    case when is_published and segment = 'All suppliers' then lw_supplied_t end as lw_supplied_t,
    case when is_published and n_farms >= 10 then p25_intensity end as p25_intensity,
    case when is_published and n_farms >= 10 then p75_intensity end as p75_intensity,
    {% for col in ['primary_intensity', 'proxy_intensity', 'avg_confidence', 'clear_share', 'n_review'] %}
    case when is_published then {{ col }} end as {{ col }}{{ "," if not loop.last }}
    {% endfor %}
from flags
