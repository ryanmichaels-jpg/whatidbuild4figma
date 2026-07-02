{{ config(materialized='table') }}

-- ACCOUNT HEAT: a decay-weighted external-intent score per company, weighted by role
-- diversity (distinct Figma surfaces) and seniority (from the contact's scraped title).
-- Runs in the warehouse; the pipeline reads a snapshot of this back into the intercept score.
-- Weights are dbt vars (see dbt_project.yml) so RevOps tunes them without touching Python.

with events as (

    select
        lower(trim(company))                                             as company,
        figma_surface,
        lead_id,
        datediff('day', run_date::date, current_date())                  as age_days
    from {{ source('pipeline', 'external_intent_events') }}

),

-- seniority from the contact observation's title (join by nothing structural in demo; in
-- production join events.lead_id -> a person key -> contact_observations)
titles as (
    select
        lower(trim(company)) as company,
        max(case
            when lower(headline) ~ '(head|vp|chief|director|principal|staff|lead)' then 1
            else 0
        end) as has_senior
    from {{ source('pipeline', 'contact_observations') }}
    group by 1
),

scored as (
    select
        e.company,
        count(*)                                                         as raw_signals,
        count(distinct e.figma_surface)                                  as surface_diversity,
        sum( power(0.5, e.age_days::float / {{ var('decay_half_life_days') }}) ) as decayed_signals,
        coalesce(max(t.has_senior), 0)                                   as has_senior
    from events e
    left join titles t on e.company = t.company
    group by e.company
)

select
    company,
    raw_signals,
    surface_diversity,
    decayed_signals,
    -- role diversity bonus + seniority multiplier -> the heat score the pipeline reads back
    round(
        decayed_signals
        * (1 + {{ var('diversity_weight') }} * (surface_diversity - 1))
        * (case when has_senior = 1 then {{ var('seniority_weight_senior') }}
                else {{ var('seniority_weight_ic') }} end)
    , 2)                                                                 as account_heat
from scored
order by account_heat desc
