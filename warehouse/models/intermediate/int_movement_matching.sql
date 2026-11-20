-- Animal-level match of herd-book sales/purchases against NLIS movements (by RFID) for NLIS-linked farms.
{% set p_start = "cast('" ~ var('period_start') ~ "' as date)" %}
{% set p_end = "cast('" ~ var('period_end') ~ "' as date)" %}
with linked as (
    select farm_id from {{ ref('stg_hp__connections') }} where has_nlis
),

book as (
    select r.farm_id, a.rfid, case r.record_type when 'sale' then 'off' else 'on' end as direction,
           r.observation_date as book_date
    from {{ ref('stg_agriwebb__records') }} r
    join {{ ref('stg_agriwebb__animals') }} a using (animal_id)
    where r.record_type in ('sale', 'purchase')
      and r.observation_date between {{ p_start }} and {{ p_end }}
      and r.farm_id in (select farm_id from linked)
),

nlis as (
    select farm_id, rfid, direction, movement_date, to_pic
    from {{ ref('stg_nlis__movements') }}
    where movement_date between {{ p_start }} and {{ p_end }}
)

select
    coalesce(b.farm_id, n.farm_id) as farm_id,
    coalesce(b.direction, n.direction) as direction,
    coalesce(b.rfid, n.rfid) as rfid,
    b.book_date,
    n.movement_date,
    n.to_pic,
    case
        when b.rfid is not null and n.rfid is not null then 'matched'
        when b.rfid is not null then 'herd_book_only'
        else 'nlis_only'
    end as match_status,
    abs({{ dbt.datediff('b.book_date', 'n.movement_date', 'day') }}) as lag_days
from book b
full outer join nlis n on n.farm_id = b.farm_id and n.rfid = b.rfid and n.direction = b.direction
