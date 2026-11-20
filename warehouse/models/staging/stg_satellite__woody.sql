select farm_id, obs_date, woody_area_ha, woody_pct from {{ source('raw', 'satellite_woody') }}
