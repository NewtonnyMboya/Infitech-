-- InfiGen banking foundation. This migration intentionally does not enable live money movement.
create extension if not exists pgcrypto;

create table if not exists public.infigen_profiles (
  user_id uuid primary key references auth.users(id) on delete cascade,
  display_name text,
  verification_status text not null default 'pending'
    check (verification_status in ('pending','in_review','verified','rejected')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.infigen_accounts (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid not null references auth.users(id) on delete cascade,
  account_type text not null check (account_type in ('demo','live')),
  currency char(3) not null default 'KES' check (currency = 'KES'),
  balance_minor bigint not null default 0 check (balance_minor >= 0),
  status text not null default 'pending'
    check (status in ('demo','pending','active','suspended','closed')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check ((account_type = 'demo' and status = 'demo') or account_type = 'live')
);

create table if not exists public.infigen_transactions (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete restrict,
  account_id uuid not null references public.infigen_accounts(id) on delete restrict,
  amount_minor bigint not null check (amount_minor > 0),
  direction text not null check (direction in ('credit','debit')),
  status text not null default 'completed' check (status in ('pending','completed','failed','reversed')),
  balance_after_minor bigint not null check (balance_after_minor >= 0),
  idempotency_key text not null,
  memo text,
  created_at timestamptz not null default now(),
  unique (user_id, idempotency_key)
);

create table if not exists public.infigen_provider_attempts (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete restrict,
  provider text not null check (provider in ('mpesa','airtel_money')),
  environment text not null default 'sandbox' check (environment in ('sandbox','production')),
  amount_minor bigint not null check (amount_minor > 0),
  status text not null default 'not_configured'
    check (status in ('not_configured','pending','succeeded','failed','cancelled')),
  provider_reference text,
  idempotency_key text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (user_id, idempotency_key)
);

create table if not exists public.infigen_audit_events (
  id bigint generated always as identity primary key,
  user_id uuid references auth.users(id) on delete set null,
  event_type text not null,
  outcome text not null check (outcome in ('success','denied','failure','info')),
  request_id text,
  details jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists infigen_accounts_owner_idx on public.infigen_accounts(owner_id);
create index if not exists infigen_transactions_user_created_idx on public.infigen_transactions(user_id, created_at desc);
create index if not exists infigen_provider_attempts_user_created_idx on public.infigen_provider_attempts(user_id, created_at desc);
create index if not exists infigen_audit_user_created_idx on public.infigen_audit_events(user_id, created_at desc);

alter table public.infigen_profiles enable row level security;
alter table public.infigen_accounts enable row level security;
alter table public.infigen_transactions enable row level security;
alter table public.infigen_provider_attempts enable row level security;
alter table public.infigen_audit_events enable row level security;

drop policy if exists "profiles_select_own" on public.infigen_profiles;
create policy "profiles_select_own" on public.infigen_profiles
  for select to authenticated using (user_id = (select auth.uid()));

drop policy if exists "accounts_select_own" on public.infigen_accounts;
create policy "accounts_select_own" on public.infigen_accounts
  for select to authenticated using (owner_id = (select auth.uid()));

drop policy if exists "transactions_select_own" on public.infigen_transactions;
create policy "transactions_select_own" on public.infigen_transactions
  for select to authenticated using (user_id = (select auth.uid()));

drop policy if exists "provider_attempts_select_own" on public.infigen_provider_attempts;
create policy "provider_attempts_select_own" on public.infigen_provider_attempts
  for select to authenticated using (user_id = (select auth.uid()));

drop policy if exists "audit_select_own" on public.infigen_audit_events;
create policy "audit_select_own" on public.infigen_audit_events
  for select to authenticated using (user_id = (select auth.uid()));

revoke all on public.infigen_profiles, public.infigen_accounts, public.infigen_transactions,
  public.infigen_provider_attempts, public.infigen_audit_events from anon, authenticated;
grant select on public.infigen_profiles, public.infigen_accounts, public.infigen_transactions,
  public.infigen_provider_attempts, public.infigen_audit_events to authenticated;

-- Atomic demo-only ledger operation. This cannot credit or debit live accounts.
create or replace function public.post_infigen_demo_transaction(
  p_account_id uuid,
  p_direction text,
  p_amount_minor bigint,
  p_idempotency_key text,
  p_memo text default null
)
returns table (transaction_id uuid, balance_after_minor bigint, transaction_status text)
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
  v_user_id uuid := auth.uid();
  v_account public.infigen_accounts%rowtype;
  v_existing public.infigen_transactions%rowtype;
  v_balance bigint;
  v_tx public.infigen_transactions%rowtype;
begin
  if v_user_id is null then
    raise exception 'Authentication required' using errcode = '28000';
  end if;
  if p_direction not in ('credit','debit') then
    raise exception 'Unsupported demo transaction direction' using errcode = '22023';
  end if;
  if p_amount_minor is null or p_amount_minor < 1 or p_amount_minor > 10000000 then
    raise exception 'Demo amount must be between KES 0.01 and KES 100,000.00' using errcode = '22023';
  end if;
  if p_idempotency_key is null or length(trim(p_idempotency_key)) < 8 or length(p_idempotency_key) > 120 then
    raise exception 'A valid idempotency key is required' using errcode = '22023';
  end if;

  select * into v_existing from public.infigen_transactions t
    where t.user_id = v_user_id and t.idempotency_key = p_idempotency_key;
  if found then
    return query select v_existing.id, v_existing.balance_after_minor, v_existing.status;
    return;
  end if;

  select * into v_account from public.infigen_accounts a
    where a.id = p_account_id and a.owner_id = v_user_id and a.account_type = 'demo' and a.status = 'demo'
    for update;
  if not found then
    raise exception 'Demo account not found or unavailable' using errcode = 'P0002';
  end if;

  -- Recheck after acquiring the account lock to make concurrent retries idempotent.
  select * into v_existing from public.infigen_transactions t
    where t.user_id = v_user_id and t.idempotency_key = p_idempotency_key;
  if found then
    return query select v_existing.id, v_existing.balance_after_minor, v_existing.status;
    return;
  end if;

  if p_direction = 'debit' and v_account.balance_minor < p_amount_minor then
    raise exception 'Insufficient demo balance' using errcode = '22003';
  end if;

  if p_direction = 'credit' then
    v_balance := v_account.balance_minor + p_amount_minor;
  else
    v_balance := v_account.balance_minor - p_amount_minor;
  end if;

  update public.infigen_accounts set balance_minor = v_balance, updated_at = now()
    where id = v_account.id;

  insert into public.infigen_transactions
    (user_id, account_id, amount_minor, direction, status, balance_after_minor, idempotency_key, memo)
  values
    (v_user_id, v_account.id, p_amount_minor, p_direction, 'completed', v_balance,
     trim(p_idempotency_key), left(coalesce(p_memo, ''), 180))
  returning * into v_tx;

  insert into public.infigen_audit_events (user_id, event_type, outcome, details)
  values (v_user_id, 'demo_transaction_posted', 'success',
    jsonb_build_object('transaction_id', v_tx.id, 'account_id', v_account.id,
      'direction', p_direction, 'amount_minor', p_amount_minor));

  return query select v_tx.id, v_tx.balance_after_minor, v_tx.status;
end;
$$;

revoke all on function public.post_infigen_demo_transaction(uuid,text,bigint,text,text) from public, anon;
grant execute on function public.post_infigen_demo_transaction(uuid,text,bigint,text,text) to authenticated;

comment on table public.infigen_accounts is 'KES balances in minor units; live accounts remain pending until separately authorized and provisioned.';
comment on table public.infigen_provider_attempts is 'Provider attempts metadata only; do not store credentials, PINs, OTPs, or full payment secrets here.';
