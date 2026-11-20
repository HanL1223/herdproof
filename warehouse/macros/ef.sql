{# Scalar lookup of a reference emission factor by key. #}
{% macro ef(factor) -%}
    (select value from {{ ref('ref_emission_factors') }} where factor = '{{ factor }}')
{%- endmacro %}
