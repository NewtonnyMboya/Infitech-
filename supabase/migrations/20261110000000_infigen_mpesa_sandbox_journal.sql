-- Sandbox-only payment request journal. This table is not a wallet ledger.
create table if not exists public.infigen_provider_payment_requests (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete restrict,
  provider text not null check (provider in ('mpesa')),
  flow text not null check (flow in ('collection','payout')),
  amount_minor bigint not null check (amount_minor between 100 and 25000000),
  currency text not null default 'KES' check (currency = 'KES'),
  phone_e164 text not null check (phone_e164 ~ '^254[17][0-9]{8}$'),
  idempotency_key text not null check (length(idempotency_key) between 16 and 100),
  status text not null default 'created' check (status in ('created','submitted','callback_received','failed','needs_reconciliation')),
  provider_request_id text,
  provider_conversation_id text,
  provider_response jsonb,
  callback_payload jsonb,
  callback_received_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (user_id, idempotency_key)
);
create index if not exists infigen_provider_payment_user_created_idx
  on public.infigen_provider_payment_requests (user_id, created_at desc);
create index if not exists infigen_provider_payment_provider_request_idx
  on public.infigen_provider_payment_requests (provider_request_id);
alter table public.infigen_provider_payment_requests enable row level security;
-- No client policies: only server-side service-role functions can read/write this journal.
