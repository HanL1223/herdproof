select
    l.lender_id,
    ld.name as lender_name,
    ld.segment as lender_segment,
    l.farm_id,
    l.facility_id,
    l.outstanding_aud,
    l.total_assets_aud,
    l.revenue_aud,
    l.declared_head
from {{ source('raw', 'hp_loans') }} l
join {{ source('raw', 'hp_lenders') }} ld using (lender_id)
