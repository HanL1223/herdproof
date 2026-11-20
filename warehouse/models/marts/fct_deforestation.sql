-- EUDR-style check: woody cover loss after the 31 Dec 2020 cut-off, from the satellite series.
{% set cutoff = "cast('2020-12-31' as date)" %}
with woody as (
    select * from {{ ref('stg_satellite__woody') }}
),

baseline as (
    select farm_id, woody_area_ha as baseline_ha, obs_date as baseline_date
    from woody
    where obs_date <= {{ cutoff }}
    qualify row_number() over (partition by farm_id order by obs_date desc) = 1
),

stats as (
    select
        w.farm_id,
        max(case when w.obs_date < b.baseline_date then w.woody_area_ha end) as pre_cutoff_max_ha,
        sum(case when w.obs_date > {{ cutoff }} then 1 else 0 end) as post_obs,
        min(case when w.obs_date > {{ cutoff }} then w.woody_area_ha end) as post_min_ha,
        max(w.obs_date) as latest_obs_date,
        min(case when w.obs_date > {{ cutoff }}
                  and w.woody_area_ha < b.baseline_ha - greatest(10, 0.02 * b.baseline_ha)
                 then w.obs_date end) as first_loss_date
    from woody w
    join baseline b using (farm_id)
    group by w.farm_id
)

select
    b.farm_id,
    b.baseline_date,
    round(b.baseline_ha, 1) as baseline_woody_ha,
    round(greatest(0, b.baseline_ha - s.post_min_ha), 1) as post_cutoff_loss_ha,
    round(greatest(0, s.pre_cutoff_max_ha - b.baseline_ha), 1) as pre_cutoff_loss_ha,
    s.post_obs,
    s.latest_obs_date,
    s.first_loss_date,
    case
        when s.post_obs < 3 then 'insufficient_data'
        when s.first_loss_date is not null then 'review'
        else 'clear'
    end as status
from baseline b
join stats s using (farm_id)
