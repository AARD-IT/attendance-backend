-- Create revoked_tokens table for access token revocation.

create table if not exists revoked_tokens (
  id bigint generated always as identity primary key,
  user_id uuid not null,
  jti text not null unique,
  token_hash bigint,
  reason text,
  revoked_at timestamptz not null default now()
);

create index if not exists idx_revoked_tokens_user_id on revoked_tokens (user_id);
