-- SchoolCore shared identity and offline sync foundation.
-- Safe additive migration: does not alter marketplace tables.
begin;
create table public.school_sync_id_map (
 id bigint generated always as identity primary key,
 school_id uuid not null references public.schools(id) on delete cascade,
 entity_type text not null check(entity_type in ('student','fee_account','fee_payment','expense','academic_term','subject','assessment','mark','attendance')),
 local_id text not null check(length(trim(local_id)) between 1 and 200),
 cloud_id uuid not null,
 created_at timestamptz not null default now(),
 updated_at timestamptz not null default now(),
 unique(school_id,entity_type,local_id),
 unique(school_id,entity_type,cloud_id)
);
create index school_sync_id_map_cloud_idx on public.school_sync_id_map(school_id,cloud_id);
alter table public.school_sync_id_map enable row level security;
create policy "members read sync id map" on public.school_sync_id_map for select to authenticated using(public.is_school_member(school_id));
create policy "school operators manage sync id map" on public.school_sync_id_map for all to authenticated using(public.has_school_role(school_id,array['admin','bursar','accountant','teacher','exams_officer'])) with check(public.has_school_role(school_id,array['admin','bursar','accountant','teacher','exams_officer']));

create table public.school_sync_outbox (
 id bigint generated always as identity primary key,
 school_id uuid not null references public.schools(id) on delete cascade,
 entity_type text not null check(entity_type in ('student','fee_account','fee_payment','expense','academic_term','subject','assessment','mark','attendance')),
 local_id text not null check(length(trim(local_id)) between 1 and 200),
 operation text not null check(operation in ('upsert','delete')),
 payload jsonb not null default '{}'::jsonb,
 idempotency_key text not null,
 status text not null default 'pending' check(status in ('pending','processing','synced','failed','conflict')),
 attempts integer not null default 0 check(attempts>=0),
 last_error text,
 created_at timestamptz not null default now(),
 updated_at timestamptz not null default now(),
 unique(school_id,idempotency_key)
);
create index school_sync_outbox_pending_idx on public.school_sync_outbox(school_id,status,created_at);
alter table public.school_sync_outbox enable row level security;
create policy "school operators read sync outbox" on public.school_sync_outbox for select to authenticated using(public.has_school_role(school_id,array['admin','bursar','accountant','teacher','exams_officer']));
create policy "school operators enqueue sync outbox" on public.school_sync_outbox for insert to authenticated with check(public.has_school_role(school_id,array['admin','bursar','accountant','teacher','exams_officer']));
create policy "school operators update sync outbox" on public.school_sync_outbox for update to authenticated using(public.has_school_role(school_id,array['admin','bursar','accountant','teacher','exams_officer']));

create or replace function public.school_upsert_student(
 p_school_id uuid,p_admission_no text,p_full_name text,p_class_name text,
 p_guardian text default null,p_guardian_phone text default null,p_local_id text default null
) returns table(student_id uuid,admission_no text,created_or_updated boolean)
language plpgsql security invoker set search_path='' as $$
declare v_student public.school_students%rowtype;
begin
 if not public.has_school_role(p_school_id,array['admin','bursar','teacher','exams_officer']) then raise exception 'Insufficient school role'; end if;
 if length(trim(coalesce(p_admission_no,'')))=0 or length(trim(coalesce(p_full_name,'')))=0 or length(trim(coalesce(p_class_name,'')))=0 then raise exception 'Admission number, student name and class are required'; end if;
 insert into public.school_students(school_id,admission_no,full_name,class_name,guardian,guardian_phone)
 values(p_school_id,upper(trim(p_admission_no)),trim(p_full_name),trim(p_class_name),nullif(trim(p_guardian),''),nullif(trim(p_guardian_phone),''))
 on conflict(school_id,admission_no) do update set full_name=excluded.full_name,class_name=excluded.class_name,
 guardian=coalesce(excluded.guardian,public.school_students.guardian),guardian_phone=coalesce(excluded.guardian_phone,public.school_students.guardian_phone),updated_at=now()
 returning * into v_student;
 if p_local_id is not null and length(trim(p_local_id))>0 then
  insert into public.school_sync_id_map(school_id,entity_type,local_id,cloud_id) values(p_school_id,'student',trim(p_local_id),v_student.id)
  on conflict(school_id,entity_type,local_id) do update set cloud_id=excluded.cloud_id,updated_at=now();
 end if;
 return query select v_student.id,v_student.admission_no,true;
end $$;
revoke all on function public.school_upsert_student(uuid,text,text,text,text,text,text) from public;
grant execute on function public.school_upsert_student(uuid,text,text,text,text,text,text) to authenticated;
commit;