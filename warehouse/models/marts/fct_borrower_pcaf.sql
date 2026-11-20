-- PCAF data quality and financed emissions per loan: lender-held proxy baseline vs HerdProof-connected evidence.
-- The API only reveals connected_* columns to a lender while the borrower's lender_share consent is active.
with px as (
    select
        max(case when proxy = 'assets' then value end) as ef_assets,
        max(case when proxy = 'revenue' then value end) as ef_revenue,
        max(case when proxy = 'head' and zone = 'tropical' then value end) as ef_head_tropical,
        max(case when proxy = 'head' and zone = 'temperate' then value end) as ef_head_temperate
    from {{ ref('ref_pcaf_proxies') }}
),

base as (
    select
        l.*,
        f.farm_name, f.region_name, f.state, f.zone,
        least(1.0, l.outstanding_aud / l.total_assets_aud) as attribution_factor,
        case when l.declared_head is not null then 3 when l.revenue_aud is not null then 4 else 5 end as baseline_score,
        case when l.declared_head is not null then '2b' when l.revenue_aud is not null then '3a' else '3b' end as baseline_option,
        case
            when l.declared_head is not null
                then l.declared_head * case when f.zone = 'tropical' then px.ef_head_tropical else px.ef_head_temperate end
            when l.revenue_aud is not null then l.revenue_aud / 1e6 * px.ef_revenue
            else l.total_assets_aud / 1e6 * px.ef_assets
        end as baseline_farm_t
    from {{ ref('stg_hp__loans') }} l
    join {{ ref('stg_hp__farms') }} f using (farm_id)
    cross join px
)

select
    b.lender_id, b.lender_name, b.lender_segment, b.facility_id, b.farm_id, b.farm_name, b.region_name, b.state, b.zone,
    b.outstanding_aud, b.total_assets_aud, b.revenue_aud, b.declared_head,
    round(b.attribution_factor, 4) as attribution_factor,
    b.baseline_score,
    b.baseline_option,
    round(b.baseline_farm_t, 1) as baseline_farm_t,
    round(b.baseline_farm_t * b.attribution_factor, 1) as baseline_financed_t,
    fp.farm_id is not null as is_connected,
    -- Score 1 also needs a clear land-use check: unassessed or post-cut-off clearing leaves land-use emissions open.
    case when fp.farm_id is null then null
         when r.coverage = 1 and r.confidence >= {{ var('pcaf_reconciled_min_confidence') }} and d.status = 'clear' then 1
         else 2 end as connected_score,
    case when fp.farm_id is null then null
         when r.coverage = 1 and r.confidence >= {{ var('pcaf_reconciled_min_confidence') }} and d.status = 'clear' then '1a'
         else '1b' end as connected_option,
    round(fp.scope1_t + fp.scope2_t, 1) as connected_farm_t,
    round((fp.scope1_t + fp.scope2_t) * b.attribution_factor, 1) as connected_financed_t,
    round(fp.intensity_kg_per_kg_lw, 2) as intensity_kg_per_kg_lw,
    r.confidence,
    r.coverage,
    r.n_fail,
    r.n_warn,
    d.status as deforestation_status,
    d.post_cutoff_loss_ha
from base b
left join {{ ref('fct_farm_footprint') }} fp using (farm_id)
left join {{ ref('fct_reconciliation') }} r using (farm_id)
left join {{ ref('fct_deforestation') }} d using (farm_id)
