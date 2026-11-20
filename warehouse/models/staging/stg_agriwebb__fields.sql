select farm_id, field_id, name as field_name, total_area_ha, grazable_area_ha, land_use
from {{ source('raw', 'agriwebb_fields') }}
