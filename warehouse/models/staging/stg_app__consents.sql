-- Active consents only; lender_share purposes carry the lender id after the colon.
select
    consent_id,
    farm_id,
    split_part(purpose, ':', 1) as purpose,
    nullif(split_part(purpose, ':', 2), '') as lender_id,
    granted_at
from {{ source('app', 'consent_ledger') }}
where revoked_at is null
