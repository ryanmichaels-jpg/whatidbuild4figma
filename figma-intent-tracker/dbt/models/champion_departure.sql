{{ config(materialized='table') }}

-- CHAMPION DEPARTURE: a contact flagged `job_change` has LEFT their Salesforce account for a
-- new company. If the account they left is a PAID customer, losing that champion is a churn
-- risk on the old account -- and the new company is a warm door (a known advocate just landed
-- there). This is the single highest-leverage join the warehouse enables.
--
-- Sources: contact_observations (this pipeline) + the Salesforce contact/account syncs.

with departures as (

    select
        sfdc_contact_id,
        name,
        company               as new_company,   -- scraped: where they are NOW
        run_date
    from {{ ref('contact_observations') }}
    where flag = 'job_change'
      and sfdc_contact_id is not null

),

sfdc as (
    select
        c.contact_id,
        a.account_name        as old_account,
        a.is_customer,
        a.plan
    from {{ source('salesforce', 'contacts') }} c
    join {{ source('salesforce', 'accounts') }} a
      on c.account_name = a.account_name
)

select
    d.name,
    s.old_account,                              -- churn_risk: paid account just lost a champion
    d.new_company,                              -- warm_door: advocate landed at a new logo
    s.plan,
    'churn_risk'          as old_account_signal,
    'warm_door'           as new_company_signal,
    d.run_date
from departures d
join sfdc s on d.sfdc_contact_id = s.contact_id
{% if var('churn_paid_only') %}
where s.is_customer = true
{% endif %}
