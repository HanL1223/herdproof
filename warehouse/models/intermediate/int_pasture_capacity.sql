-- Satellite-implied carrying capacity (adult equivalents) vs the herd recorded in AgriWebb.
with pasture as (
    select farm_id, avg(tsdm_kg_ha) as avg_tsdm_kg_ha, avg(ground_cover_pct) as avg_ground_cover_pct
    from {{ ref('stg_satellite__pasture') }}
    group by farm_id
),

herd as (
    select farm_id, sum(ae_years) as herd_ae
    from {{ ref('int_herd_class_quarters') }}
    group by farm_id
),

paddocks as (
    select farm_id, sum(total_area_ha) as mapped_area_ha, sum(grazable_area_ha) as grazable_area_ha
    from {{ ref('stg_agriwebb__fields') }}
    group by farm_id
)

select
    b.farm_id,
    b.boundary_area_ha,
    pd.mapped_area_ha,
    pd.grazable_area_ha,
    p.avg_tsdm_kg_ha,
    p.avg_ground_cover_pct,
    p.avg_tsdm_kg_ha * b.boundary_area_ha * 0.9 * {{ ef('pasture_turnover') }} * {{ ef('pasture_utilisation') }}
        / ({{ ef('ae_daily_intake') }} * 365) as capacity_ae,
    h.herd_ae
from {{ ref('stg_satellite__boundary') }} b
join pasture p using (farm_id)
left join paddocks pd using (farm_id)
left join herd h using (farm_id)
