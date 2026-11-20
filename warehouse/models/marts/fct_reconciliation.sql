select
    c.farm_id,
    s.has_agriwebb, s.has_nlis, s.has_satellite,
    round(100 * sum(case when c.assessed then c.weight * c.score else 0 end)
        / nullif(sum(case when c.assessed then c.weight else 0 end), 0), 1) as confidence,
    round(sum(case when c.assessed then c.weight else 0 end) * 1.0 / sum(c.weight), 3) as coverage,
    sum(case when c.status = 'fail' then 1 else 0 end) as n_fail,
    sum(case when c.status = 'warn' then 1 else 0 end) as n_warn
from {{ ref('fct_reconciliation_checks') }} c
join {{ ref('stg_hp__connections') }} s using (farm_id)
group by c.farm_id, s.has_agriwebb, s.has_nlis, s.has_satellite
