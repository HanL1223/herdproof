select
    farm_id,
    coalesce(diesel_l, 0) as diesel_l,
    coalesce(petrol_l, 0) as petrol_l,
    coalesce(electricity_kwh, 0) as electricity_kwh,
    coalesce(renewable_fraction, 0) as renewable_fraction,
    coalesce(fertiliser_n_kg, 0) as fertiliser_n_kg,
    coalesce(urea_kg, 0) as urea_kg,
    coalesce(lime_t, 0) as lime_t,
    coalesce(plantings_ha, 0) as plantings_ha
from {{ source('raw', 'hp_farm_inputs') }}
