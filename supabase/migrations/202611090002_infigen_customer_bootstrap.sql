-- InfiGen authenticated customer bootstrap.
-- Call after sign-in. It creates only the authenticated user's profile and demo account.
create or replace function public.ensure_infigen_customer(p_display_name text default null)
returns jsonb
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
  v_user_id uuid := auth.uid();
  v_account_id uuid;
begin
  if v_user_id is null then
    raise exception 'Authentication required' using errcode = '28000';
  end if;

  insert into public.infigen_profiles (user_id, display_name)
  values (v_user_id, nullif(left(trim(coalesce(p_display_name, '')), 100), ''))
  on conflict (user_id) do update
    set display_name = coalesce(
      nullif(left(trim(coalesce(excluded.display_name, '')), 100), ''),
      public.infigen_profiles.display_name
    ),
    updated_at = now();

  select a.id into v_account_id
  from public.infigen_accounts a
  where a.owner_id = v_user_id and a.account_type = 'demo' and a.status = 'demo'
  order by a.created_at
  limit 1;

  if v_account_id is null then
    insert into public.infigen_accounts
      (owner_id, account_type, currency, balance_minor, status)
    values
      (v_user_id, 'demo', 'KES', 1000000, 'demo')
    returning id into v_account_id;
  end if;

  insert into public.infigen_audit_events (user_id, event_type, outcome, details)
  values (v_user_id, 'customer_session_initialized', 'success',
    jsonb_build_object('demo_account_id', v_account_id));

  return jsonb_build_object('account_id', v_account_id, 'currency', 'KES');
end;
$$;

revoke all on function public.ensure_infigen_customer(text) from public, anon;
grant execute on function public.ensure_infigen_customer(text) to authenticated;
