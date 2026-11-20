-- Independent cross-checks of the herd book; each check scores 0-1 and is weighted in fct_reconciliation.
with farms as (
    select c.* from {{ ref('stg_hp__connections') }} c where c.has_agriwebb
),

movement as (
    select
        farm_id, direction,
        sum(case when match_status = 'matched' then 1 else 0 end) as matched,
        sum(case when match_status = 'herd_book_only' then 1 else 0 end) as herd_only,
        sum(case when match_status = 'nlis_only' then 1 else 0 end) as nlis_only,
        sum(case when match_status = 'matched' and lag_days > 7 then 1 else 0 end) as lagged
    from {{ ref('int_movement_matching') }}
    group by farm_id, direction
),

movement_checks as (
    select
        f.farm_id,
        d.check_id,
        f.has_nlis as assessed,
        coalesce(m.matched * 1.0 / nullif(m.matched + m.herd_only + m.nlis_only, 0), 1.0) as score,
        coalesce(m.matched, 0) as observed,
        coalesce(m.matched + m.herd_only + m.nlis_only, 0) as expected,
        coalesce(m.matched, 0) || ' matched, ' || coalesce(m.herd_only, 0) || ' in herd book only, '
            || coalesce(m.nlis_only, 0) || ' in NLIS only, ' || coalesce(m.lagged, 0) || ' lagged >7 days' as detail
    from farms f
    cross join (select 'nlis_sales' as check_id, 'off' as direction union all select 'nlis_purchases', 'on') d
    left join movement m on m.farm_id = f.farm_id and m.direction = d.direction
),

herd as (
    select
        h.farm_id,
        h.closing_head, h.expected_closing_head, h.deaths,
        q.head_days / 365.0 as avg_head,
        q.evidenced_days * 1.0 / q.head_days as weight_coverage
    from {{ ref('int_herd_flows') }} h
    join (
        select farm_id, sum(head_days) as head_days, sum(evidenced_days) as evidenced_days
        from {{ ref('int_herd_class_quarters') }} group by farm_id
    ) q using (farm_id)
),

herd_checks as (
    select farm_id, 'herd_balance' as check_id, true as assessed,
           greatest(0, 1 - 10 * abs(closing_head - expected_closing_head) * 1.0 / greatest(closing_head, 1)) as score,
           closing_head as observed, expected_closing_head as expected,
           'Closing ' || closing_head || ' head vs ' || expected_closing_head || ' implied by recorded events' as detail
    from herd
    union all
    select farm_id, 'mortality', true,
           case when deaths / avg_head between 0.003 and 0.08 then 1.0 else 0.5 end,
           round(100 * deaths / avg_head, 1), null,
           round(100 * deaths / avg_head, 1) || '% annual mortality'
    from herd
    union all
    select farm_id, 'weight_coverage', true, weight_coverage, round(100 * weight_coverage, 1), 100,
           round(100 * weight_coverage, 1) || '% of animal-days backed by a weigh record'
    from herd
),

land_checks as (
    select f.farm_id, 'stocking_vs_pasture' as check_id, f.has_satellite as assessed,
           case when p.herd_ae / p.capacity_ae <= 1.2 then 1.0
                else greatest(0, 1 - (p.herd_ae / p.capacity_ae - 1.2) / 0.4) end as score,
           round(p.herd_ae, 0) as observed, round(p.capacity_ae, 0) as expected,
           round(p.herd_ae, 0) || ' AE recorded vs ' || round(p.capacity_ae, 0) || ' AE pasture capacity' as detail
    from farms f left join {{ ref('int_pasture_capacity') }} p using (farm_id)
    union all
    select f.farm_id, 'land_area', f.has_satellite,
           greatest(0, 1 - greatest(0, abs(1 - p.mapped_area_ha / p.boundary_area_ha) - 0.05) / 0.25),
           round(p.mapped_area_ha, 0), round(p.boundary_area_ha, 0),
           round(100 * p.mapped_area_ha / p.boundary_area_ha, 0) || '% of satellite boundary mapped as paddocks'
    from farms f left join {{ ref('int_pasture_capacity') }} p using (farm_id)
),

checks as (
    select * from movement_checks
    union all select * from herd_checks
    union all select * from land_checks
)

select
    c.farm_id,
    c.check_id,
    r.label,
    r.weight,
    c.assessed,
    case when not c.assessed then null else round(c.score, 3) end as score,
    case when not c.assessed then 'not_assessed'
         when c.score >= 0.9 then 'pass'
         when c.score >= 0.7 then 'warn'
         else 'fail' end as status,
    c.observed,
    c.expected,
    case when c.assessed then c.detail else 'Source not connected' end as detail
from checks c
join {{ ref('ref_reconciliation_checks') }} r using (check_id)
