select
    m.farm_id,
    m.transaction_id,
    m.nlis_id,
    m.rfid,
    m.from_pic,
    m.to_pic,
    m.movement_date,
    m.nvd_number,
    m.movement_type,
    case when m.from_pic = f.pic then 'off' when m.to_pic = f.pic then 'on' end as direction
from {{ source('raw', 'nlis_movements') }} m
join {{ source('raw', 'hp_farms') }} f using (farm_id)
where m.species = 'Cattle'
