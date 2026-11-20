-- FY quarters mapped to GAF seasons (Jul-Sep winter ... Apr-Jun autumn); end dates are exclusive.
{% set start = "cast('" ~ var('period_start') ~ "' as date)" %}
with quarters as (
    select 1 as quarter, 'winter' as season union all
    select 2, 'spring' union all
    select 3, 'summer' union all
    select 4, 'autumn'
)
select
    quarter,
    season,
    cast({{ dbt.dateadd('month', '3 * (quarter - 1)', start) }} as date) as start_date,
    cast({{ dbt.dateadd('month', '3 * quarter', start) }} as date) as end_date
from quarters
