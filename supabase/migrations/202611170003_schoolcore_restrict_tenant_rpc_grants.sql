-- Keep tenant bootstrap and staff management RPCs authenticated-only.
revoke all on function public.create_school(text,text,text) from public, anon;
grant execute on function public.create_school(text,text,text) to authenticated;
revoke all on function public.add_school_member(uuid,text,text) from public, anon;
grant execute on function public.add_school_member(uuid,text,text) to authenticated;
revoke all on function public.has_school_role(uuid,text[]) from public, anon;
grant execute on function public.has_school_role(uuid,text[]) to authenticated;
revoke all on function public.is_school_member(uuid) from public, anon;
grant execute on function public.is_school_member(uuid) to authenticated;
