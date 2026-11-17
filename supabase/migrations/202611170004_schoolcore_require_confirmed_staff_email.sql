create or replace function public.add_school_member(p_school uuid, p_email text, p_role text)
returns void
language plpgsql
security definer
set search_path to ''
as $function$
declare uid uuid;
begin
  if not public.has_school_role(p_school, array['admin']) then
    raise exception 'School admin role required';
  end if;
  if p_role not in ('admin','bursar','accountant','teacher','exams_officer','viewer') then
    raise exception 'Invalid role';
  end if;
  select id into uid
  from auth.users
  where lower(email)=lower(trim(p_email))
    and email_confirmed_at is not null;
  if uid is null then
    raise exception 'User must register and confirm their email with Supabase Auth first';
  end if;
  insert into public.school_member_roles(school_id,user_id,role)
  values(p_school,uid,p_role)
  on conflict(school_id,user_id)
  do update set role=excluded.role;
end
$function$;
revoke all on function public.add_school_member(uuid,text,text) from public, anon;
grant execute on function public.add_school_member(uuid,text,text) to authenticated;
