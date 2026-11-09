-- M-PESA STK collection intent foundation.
-- This migration records payment attempts only. A callback must never credit a balance by itself.
create extension if not exists pgcrypto;

create table if not exists public.infigen_payment_intents (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete restrict,
  account_id uuid not null references public.infigen_accounts(id) on delete restrict,
  provider text not null check (provider in ('mpesa')),
  flow text not null default 'collection' check (flow = 'collection'),
  environment text not null check (environment in ('sandbox','production')),
  amount_minor bigint not null check (amount_minor between 100 and 10000000 and amount_minor % 100 = 0),
  currency char(3) not null default 'KES' check (currency = 'KES'),
  phone_e164 text not null check (phone_e164 ~ '^254[17][0-9]{8}$'),
  account_reference text not null check (length(account_reference) between 1 and 12),
  transaction_description text not null check (length(transaction_description) between 1 and 80),
  idempotency_key text not null check (length(idempotency_key) between 8 and 120),
  status text not null default 'pending'
    check (status in ('pending','provider_accepted','callback_received_pending_verification',
      'succeeded_verified','failed_verified','cancelled_verified','unknown')),
  provider_checkout_request_id text unique,
  provider_merchant_request_id text,
  provider_receipt text unique,
  provider_result_code integer,
  provider_result_description text,
  callback_received_at timestamptz,
  verified_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (user_id, idempotency_key),
  unique (id, user_id),
  check ((status <> 'succeeded_verified') or (verified_at is not null and provider_receipt is not null))
);

create index if not exists infigen_payment_intents_user_created_idx
  on public.infigen_payment_intents(user_id, created_at desc);
create index if not exists infigen_payment_intents_pending_idx
  on public.infigen_payment_intents(status, created_at)
  where status in ('pending','provider_accepted','callback_received_pending_verification','unknown');

create table if not exists public.infigen_provider_events (
  id bigint generated always as identity primary key,
  provider text not null check (provider = 'mpesa'),
  event_hash text not null unique check (length(event_hash) = 64),
  checkout_request_id text,
  result_code integer,
  result_description text,
  receipt_reference text,
  amount_minor bigint,
  phone_last4 text,
  received_at timestamptz not null default now(),
  verification_status text not null default 'pending'
    check (verification_status in ('pending','verified','rejected')),
  verified_at timestamptz,
  safe_metadata jsonb not null default '{}'::jsonb
);

create index if not exists infigen_provider_events_checkout_idx
  on public.infigen_provider_events(checkout_request_id, received_at desc);

alter table public.infigen_payment_intents enable row level security;
alter table public.infigen_provider_events enable row level security;

drop policy if exists "payment_intents_select_own" on public.infigen_payment_intents;
create policy "payment_intents_select_own" on public.infigen_payment_intents
  for select to authenticated using (user_id = (select auth.uid()));

revoke all on public.infigen_payment_intents, public.infigen_provider_events from public, anon, authenticated;
grant select on public.infigen_payment_intents to authenticated;

comment on table public.infigen_payment_intents is
  'M-PESA STK collection intents. Only server-side verified provider results may transition to a verified terminal state or post a ledger entry.';
comment on table public.infigen_provider_events is
  'Redacted M-PESA callback metadata. Public callback receipt is untrusted until reconciled against Daraja status API.';
