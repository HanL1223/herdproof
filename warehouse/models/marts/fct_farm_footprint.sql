-- Farm footprint following the GAF beef method (simplified port of the AIA EAP engine; see README).
with farms as (
    select * from {{ ref('stg_hp__farms') }}
),

classes as (
    select
        c.*,
        f.zone, f.north_of_capricorn, f.rainfall_above_600,
        d.dmd_pct, d.cp_pct,
        case when c.gaf_class in ('steersLt1', 'steers1To2', 'steersGt2', 'bullsGt1') then 700.0 else 550.0 end as srw_kg,
        power(1.185 + 0.00454 * c.liveweight_kg - 0.0000026 * c.liveweight_kg * c.liveweight_kg, 2) as maint_dmi,
        power(1.185 + 0.00454 * c.liveweight_kg - 0.0000026 * c.liveweight_kg * c.liveweight_kg
              + 0.315 * greatest(c.liveweight_gain_kg_day, 0), 2)
            * case when c.gaf_class = 'cowsGt2' then 1 + 0.25 * c.nursing_fraction else 1 end as dmi_kg_day
    from {{ ref('int_herd_class_quarters') }} c
    join farms f using (farm_id)
    join {{ ref('ref_diet_quality') }} d on d.zone = f.zone and d.quarter = c.quarter
    where c.gaf_class <> 'calves'  -- pre-weaning intake is carried by the lactation uplift on cows
),

nitrogen as (
    select
        *,
        (0.3 * (dmi_kg_day * cp_pct / 100) * (1 - (dmd_pct + 10) / 100)
            + 0.105 * ((0.1604 * dmd_pct - 1.037) * dmi_kg_day * 0.008)
            + 0.0152 * dmi_kg_day) / 6.25 as faecal_n_kg_day,
        greatest(0, ((0.212 - 0.008 * (dmi_kg_day / maint_dmi - 2)
            - (0.14 - 0.008 * (dmi_kg_day / maint_dmi - 2)) / (1 + exp(-6 * (liveweight_kg / srw_kg - 0.4))))
            * (liveweight_gain_kg_day * 0.92)) / 6.25) as retained_n_kg_day
    from classes
),

livestock as (
    select
        farm_id,
        sum(head_days * {{ ef('ch4_yield_g_per_kg_dmi') }} * dmi_kg_day) / 1e6 as enteric_ch4_t,
        sum(head_days * dmi_kg_day * (1 - dmd_pct / 100)
            * case when north_of_capricorn then {{ ef('manure_ch4_ef_warm') }} else {{ ef('manure_ch4_ef_temperate') }} end) / 1000 as manure_ch4_t,
        sum(head_days * (faecal_n_kg_day + greatest(0, cp_pct / 100 * dmi_kg_day / 6.25 - retained_n_kg_day - faecal_n_kg_day
            - 0.00011 * power(liveweight_kg, 0.75) / 6.25))) as excreta_n_kg,
        sum(head_days) / 365.0 as avg_head,
        sum(ae_years) as herd_ae
    from nitrogen
    group by farm_id
),

calc as (
    select
        f.farm_id,
        l.avg_head,
        l.herd_ae,
        l.enteric_ch4_t * {{ ef('gwp_ch4') }} as enteric_t,
        l.manure_ch4_t * {{ ef('gwp_ch4') }} as manure_ch4_co2e_t,
        l.excreta_n_kg * ({{ ef('ef_urine_dung_n2o') }} + {{ ef('frac_gasm') }} * {{ ef('ef_atm_deposition') }}
            + case when f.rainfall_above_600 then {{ ef('frac_leach') }} * {{ ef('ef_leach') }} else 0 end)
            * 44 / 28 / 1000 * {{ ef('gwp_n2o') }} as excreta_n2o_t,
        (i.fertiliser_n_kg + i.urea_kg * {{ ef('urea_n_content') }})
            * ({{ ef('ef_fert_n_pasture') }} + {{ ef('frac_gasf') }} * {{ ef('ef_atm_deposition') }}
            + case when f.rainfall_above_600 then {{ ef('frac_leach') }} * {{ ef('ef_leach') }} else 0 end)
            * 44 / 28 / 1000 * {{ ef('gwp_n2o') }} as fertiliser_n2o_t,
        i.urea_kg / 1000 * {{ ef('urea_co2') }} + i.lime_t * {{ ef('lime_co2') }} as urea_lime_co2_t,
        (i.diesel_l * {{ ef('diesel_kg_per_l') }} + i.petrol_l * {{ ef('petrol_kg_per_l') }}) / 1000 as fuel_t,
        i.electricity_kwh * (1 - i.renewable_fraction) * e.scope2_kg_per_kwh / 1000 as scope2_t,
        h.purchased_lw_kg * case when f.zone = 'tropical' then {{ ef('purchased_cattle_north') }}
                                 else {{ ef('purchased_cattle_south') }} end / 1000 as scope3_purchased_t,
        i.plantings_ha * case when f.zone = 'tropical' then {{ ef('plantings_seq_tropical') }}
                              else {{ ef('plantings_seq_temperate') }} end as sequestration_t,
        h.lw_produced_kg,
        h.sold_lw_kg,
        h.purchased_lw_kg,
        i.renewable_fraction,
        i.plantings_ha,
        i.fertiliser_n_kg + i.urea_kg * {{ ef('urea_n_content') }} as fertiliser_n_kg
    from farms f
    join livestock l using (farm_id)
    join {{ ref('int_herd_flows') }} h using (farm_id)
    left join {{ ref('stg_hp__farm_inputs') }} i using (farm_id)
    left join {{ ref('ref_electricity_factors') }} e on e.state = f.state
)

select
    *,
    enteric_t + manure_ch4_co2e_t + excreta_n2o_t + fertiliser_n2o_t + urea_lime_co2_t + fuel_t as scope1_t,
    enteric_t + manure_ch4_co2e_t + excreta_n2o_t + fertiliser_n2o_t + urea_lime_co2_t + fuel_t
        + scope2_t + scope3_purchased_t as gross_t,
    (enteric_t + manure_ch4_co2e_t + excreta_n2o_t + fertiliser_n2o_t + urea_lime_co2_t + fuel_t
        + scope2_t + scope3_purchased_t) * 1000 / nullif(lw_produced_kg, 0) as intensity_kg_per_kg_lw,
    (enteric_t + manure_ch4_co2e_t + excreta_n2o_t + fertiliser_n2o_t + urea_lime_co2_t + fuel_t
        + scope2_t + scope3_purchased_t - sequestration_t) * 1000 / nullif(lw_produced_kg, 0) as net_intensity_kg_per_kg_lw
from calc
