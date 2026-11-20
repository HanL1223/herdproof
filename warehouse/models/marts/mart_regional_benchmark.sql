-- Benchmarks only from farms that granted regional_benchmark consent; groups smaller than k are not published.
with pool as (
    select fp.farm_id, f.region_code, f.region_name, f.state, fp.intensity_kg_per_kg_lw,
           fp.gross_t / nullif(fp.avg_head, 0) as t_per_head
    from {{ ref('fct_farm_footprint') }} fp
    join {{ ref('stg_hp__farms') }} f using (farm_id)
    where fp.farm_id in (select farm_id from {{ ref('stg_app__consents') }} where purpose = 'regional_benchmark')
),

agg as (
{% set groups = [("region", "region_code", "max(region_name)"), ("state", "state", "max(state)"), ("national", "'AU'", "'Australia'")] %}
{% for level, key, label in groups %}
    select
        '{{ level }}' as level,
        {{ key }} as benchmark_key,
        {{ label }} as benchmark_name,
        count(*) as n_farms,
        percentile_cont(0.25) within group (order by intensity_kg_per_kg_lw) as p25_intensity,
        percentile_cont(0.5) within group (order by intensity_kg_per_kg_lw) as median_intensity,
        percentile_cont(0.75) within group (order by intensity_kg_per_kg_lw) as p75_intensity,
        percentile_cont(0.5) within group (order by t_per_head) as median_t_per_head
    from pool
    group by 2  -- benchmark_key
    {% if not loop.last %}union all{% endif %}
{% endfor %}
),

-- Complementary suppression: a level publishes only if every segment in it meets k,
-- so a suppressed segment cannot be derived from its siblings and the parent total.
flags as (
    select *, min(n_farms) over (partition by level) >= {{ var('benchmark_min_farms') }} as is_published
    from agg
)

select
    level,
    benchmark_key,
    benchmark_name,
    n_farms,
    -- Spreads need n >= 10, as in the processor cohort.
    case when is_published and n_farms >= 10 then p25_intensity end as p25_intensity,
    case when is_published then median_intensity end as median_intensity,
    case when is_published and n_farms >= 10 then p75_intensity end as p75_intensity,
    case when is_published then median_t_per_head end as median_t_per_head,
    is_published
from flags
