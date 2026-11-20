select farm_id, provider, boundary_area_ha from {{ source('raw', 'satellite_boundary') }}
