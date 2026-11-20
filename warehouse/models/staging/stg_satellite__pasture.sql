select farm_id, obs_date, tsdm_kg_ha, ground_cover_pct from {{ source('raw', 'satellite_pasture') }}
