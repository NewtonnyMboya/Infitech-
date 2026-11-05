-- InfiGen marketplace: Supabase PostgreSQL foundation
-- Apply in Supabase SQL Editor. Keep service-role credentials server-side only.

create extension if not exists pgcrypto;

create table if not exists public.products (
  id text primary key check (id ~ '^[a-z0-9][a-z0-9-]{1,59}$'),
  name text not null,
  category text not null,
  description text not null,
  price_kes integer not null check (price_kes between 1 and 150000),
  image text not null default '',
  license_required boolean not null default false,
  file_name text,
  version text not null default '',
  compatibility text not null default '',
  active boolean not null default false,
  rights_basis text not null default '' check (rights_basis in ('', 'owned', 'authorized_reseller', 'open_source_compliant')),
  source_url text not null default '',
  license_url text not null default '',
  proof_reference text not null default '',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists products_active_idx on public.products (active, category);

create table if not exists public.orders (
  id text primary key,
  created_at timestamptz not null default now(),
  email text not null,
  phone_number text not null,
  amount_kes integer not null check (amount_kes between 1 and 150000),
  currency text not null default 'KES' check (currency = 'KES'),
  status text not null check (status in ('payment_pending','payment_initiation_failed','payment_failed','payment_verification_pending','paid')),
  payment_provider text not null default 'mpesa-daraja',
  environment text not null check (environment in ('sandbox','production')),
  access_token_hash text not null,
  checkout_request_id text unique,
  merchant_request_id text,
  receipt text,
  paid_at timestamptz,
  provider_response_code text,
  failure_reason text,
  callback_result jsonb,
  updated_at timestamptz not null default now()
);

create index if not exists orders_status_created_idx on public.orders (status, created_at);
create index if not exists orders_email_created_idx on public.orders (email, created_at desc);

create table if not exists public.order_items (
  id bigint generated always as identity primary key,
  order_id text not null references public.orders(id) on delete cascade,
  product_id text not null,
  product_name text not null,
  unit_price_kes integer not null check (unit_price_kes > 0),
  quantity integer not null check (quantity between 1 and 5),
  license_required boolean not null default false,
  file_name text
);
create index if not exists order_items_order_idx on public.order_items(order_id);

create table if not exists public.entitlements (
  id uuid primary key default gen_random_uuid(),
  order_id text not null references public.orders(id) on delete cascade,
  product_id text not null,
  download_token_hash text not null unique,
  download_expires_at timestamptz not null,
  license_key text,
  created_at timestamptz not null default now()
);
create index if not exists entitlements_order_idx on public.entitlements(order_id);

-- No browser role may read or mutate marketplace records directly.
alter table public.products enable row level security;
alter table public.orders enable row level security;
alter table public.order_items enable row level security;
alter table public.entitlements enable row level security;

revoke all on public.products, public.orders, public.order_items, public.entitlements from anon, authenticated;
grant all on public.products, public.orders, public.order_items, public.entitlements to service_role;
grant usage, select on sequence public.order_items_id_seq to service_role;

-- Private product files. Backend must issue short-lived signed URLs after entitlement checks.
insert into storage.buckets (id, name, public, file_size_limit)
values ('infigen-products', 'infigen-products', false, 104857600)
on conflict (id) do update set public = false, file_size_limit = excluded.file_size_limit;

-- No anon/authenticated Storage policies are created. Service role only.
