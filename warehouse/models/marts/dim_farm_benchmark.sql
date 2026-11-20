-- Each footprinted farm gets the most local published benchmark (region, then state, then national).
with published as (
    select * from {{ ref('mart_regional_benchmark') }} where is_published
),

picked as (
    select
        f.farm_id,
        fp.intensity_kg_per_kg_lw,
        coalesce(r.level, s.level, n.level) as level,
        coalesce(r.benchmark_name, s.benchmark_name, n.benchmark_name) as benchmark_name,
        coalesce(r.n_farms, s.n_farms, n.n_farms) as n_farms,
        case when r.level is not null then r.p25_intensity when s.level is not null then s.p25_intensity else n.p25_intensity end as p25_intensity,
        coalesce(r.median_intensity, s.median_intensity, n.median_intensity) as median_intensity,
        case when r.level is not null then r.p75_intensity when s.level is not null then s.p75_intensity else n.p75_intensity end as p75_intensity
    from {{ ref('fct_farm_footprint') }} fp
    join {{ ref('stg_hp__farms') }} f using (farm_id)
    left join published r on r.level = 'region' and r.benchmark_key = f.region_code
    left join published s on s.level = 'state' and s.benchmark_key = f.state
    left join published n on n.level = 'national'
)

select
    *,
    case
        when p25_intensity is null then case when intensity_kg_per_kg_lw <= median_intensity then 'top half' else 'bottom half' end
        when intensity_kg_per_kg_lw <= p25_intensity then 'top quartile'
        when intensity_kg_per_kg_lw <= median_intensity then 'second quartile'
        when intensity_kg_per_kg_lw <= p75_intensity then 'third quartile'
        else 'bottom quartile'
    end as quartile,
    round(100 * (intensity_kg_per_kg_lw / median_intensity - 1), 1) as pct_vs_median
from picked
