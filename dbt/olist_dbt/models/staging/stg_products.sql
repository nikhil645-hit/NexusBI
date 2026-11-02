-- ==============================================================================
-- stg_products.sql - Cleansed Products Staging View
-- Purpose:
--   Enriches products with English translated category names from category_translation.
--   Casts dimensions and weights to standardized numeric types. Drops Airbyte metadata.
-- ==============================================================================

with products as (
    select * from {{ source('raw', 'products') }}
),

translations as (
    select * from {{ source('raw', 'category_translation') }}
),

joined as (
    select
        cast(p.product_id as varchar(64)) as product_id,
        cast(p.product_category_name as varchar(100)) as category_name_portuguese,
        coalesce(
            cast(t.product_category_name_english as varchar(100)),
            cast(p.product_category_name as varchar(100)),
            'unknown'
        ) as category_name,
        cast(p.product_name_lenght as integer) as product_name_length,
        cast(p.product_description_lenght as integer) as product_description_length,
        cast(p.product_photos_qty as integer) as product_photos_qty,
        cast(p.product_weight_g as numeric(10,2)) as weight_g,
        cast(p.product_length_cm as numeric(10,2)) as length_cm,
        cast(p.product_height_cm as numeric(10,2)) as height_cm,
        cast(p.product_width_cm as numeric(10,2)) as width_cm
    from products p
    left join translations t
        on p.product_category_name = t.product_category_name
)

select * from joined

