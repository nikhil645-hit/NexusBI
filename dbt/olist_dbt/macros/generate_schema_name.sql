-- ==============================================================================
-- macros/generate_schema_name.sql - Custom Schema Name Resolver
--
-- Overrides dbt's default behavior of prefixing target schema (staging_marts -> marts)
-- This ensures models land directly in `staging` and `marts` schemas.
-- ==============================================================================

{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- if custom_schema_name is none -%}
        {{ target.schema }}
    {%- else -%}
        {{ custom_schema_name | trim }}
    {%- endif -%}
{%- endmacro %}

