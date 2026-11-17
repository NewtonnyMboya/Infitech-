-- SchoolCore unified finance and academic database; apply with Supabase CLI.
begin;
create extension if not exists pgcrypto;

create table public.schools(id uuid primary key default gen_random_uuid(),name text not null check(length(trim(name)) between 1 and 160),school_code text,county text,currency_code char(3) not null default 'KES',created_at timestamptz not null default now(),updated_at timestamptz not null default now());
create table public.profiles(id uuid primary key references auth.users(id) on delete cascade,display_name text,created_at timestamptz not null default now(),updated_at timestamptz not null default now());
create table public.school_members(school_id uuid not null references public.schools(id) on delete cascade,user_id uuid not null references auth.users(id) on delete cascade,role text not null check(role in ('admin','bursar','accountant','teacher','exams_officer','viewer')),created_at timestamptz not null default now(),primary key(school_id,user_id));
create table public.students(id uuid primary key default gen_random_uuid(),school_id uuid not null references public.schools(id) on delete cascade,admission_no text not null,full_name text not null,class_name text not null,guardian text,guardian_phone text,status text not null default 'active' check(status in ('active','inactive','graduated','transferred')),created_at timestamptz not null default now(),updated_at timestamptz not null default now(),unique(school_id,admission_no),unique(school_id,id));
create table public.fee_accounts(id uuid primary key default gen_random_uuid(),school_id uuid not null references public.schools(id) on delete cascade,student_id uuid not null,academic_year integer not null,description text not null default 'School fees',amount_due numeric(14,2) not null check(amount_due>=0),created_at timestamptz not null default now(),updated_at timestamptz not null default now(),foreign key(school_id,student_id) references public.students(school_id,id) on delete restrict,unique(school_id,student_id,academic_year,description));
create table public.fee_payments(id uuid primary key default gen_random_uuid(),school_id uuid not null references public.schools(id) on delete cascade,student_id uuid not null,receipt_no text not null,amount numeric(14,2) not null check(amount>0),method text not null check(method in ('Cash','M-Pesa','Bank transfer','Cheque','Other')),reference text,paid_at date not null default current_date,recorded_by uuid references auth.users(id),created_at timestamptz not null default now(),foreign key(school_id,student_id) references public.students(school_id,id) on delete restrict,unique(school_id,receipt_no));
create table public.expenses(id uuid primary key default gen_random_uuid(),school_id uuid not null references public.schools(id) on delete cascade,category text not null,description text not null,amount numeric(14,2) not null check(amount>0),method text not null check(method in ('Cash','M-Pesa','Bank transfer','Cheque','Other')),reference text,expense_date date not null default current_date,recorded_by uuid references auth.users(id),created_at timestamptz not null default now());
create table public.academic_terms(id uuid primary key default gen_random_uuid(),school_id uuid not null references public.schools(id) on delete cascade,academic_year integer not null,term_name text not null,starts_on date,ends_on date,created_at timestamptz not null default now(),unique(school_id,academic_year,term_name),unique(school_id,id));
create table public.subjects(id uuid primary key default gen_random_uuid(),school_id uuid not null references public.schools(id) on delete cascade,code text,name text not null,active boolean not null default true,created_at timestamptz not null default now(),unique(school_id,id),unique(school_id,code));
create table public.assessments(id uuid primary key default gen_random_uuid(),school_id uuid not null references public.schools(id) on delete cascade,term_id uuid not null,name text not null,assessment_type text,max_score numeric(8,2) not null check(max_score>0),weight numeric(7,3) not null default 100 check(weight>0),held_on date,created_at timestamptz not null default now(),foreign key(school_id,term_id) references public.academic_terms(school_id,id) on delete cascade,unique(school_id,id));
create table public.marks(id uuid primary key default gen_random_uuid(),school_id uuid not null references public.schools(id) on delete cascade,assessment_id uuid not null,student_id uuid not null,subject_id uuid not null,score numeric(8,2) not null check(score>=0),remarks text,entered_by uuid references auth.users(id),created_at timestamptz not null default now(),updated_at timestamptz not null default now(),foreign key(school_id,assessment_id) references public.assessments(school_id,id) on delete cascade,foreign key(school_id,student_id) references public.students(school_id,id) on delete cascade,foreign key(school_id,subject_id) references public.subjects(school_id,id) on delete restrict,unique(school_id,assessment_id,student_id,subject_id));
create table public.attendance(id uuid primary key default gen_random_uuid(),school_id uuid not null references public.schools(id) on delete cascade,student_id uuid not null,attendance_date date not null,status text not null check(status in ('present','absent','late','excused')),note text,recorded_by uuid references auth.users(id),created_at timestamptz not null default now(),foreign key(school_id,student_id) references public.students(school_id,id) on delete cascade,unique(school_id,student_id,attendance_date));
create table public.audit_events(id bigint generated always as identity primary key,school_id uuid not null references public.schools(id) on delete cascade,actor_id uuid references auth.users(id),action text not null,entity text not null,entity_id text,metadata jsonb not null default '{}'::jsonb,created_at timestamptz not null default now());

create function public.is_school_member(p_school uuid) returns boolean language sql stable security definer set search_path='' as $$ select exists(select 1 from public.school_members m where m.school_id=p_school and m.user_id=(select auth.uid())) $$;
create function public.has_school_role(p_school uuid,p_roles text[]) returns boolean language sql stable security definer set search_path='' as $$ select exists(select 1 from public.school_members m where m.school_id=p_school and m.user_id=(select auth.uid()) and m.role=any(p_roles)) $$;
revoke all on function public.is_school_member(uuid) from public;
revoke all on function public.has_school_role(uuid,text[]) from public;
grant execute on function public.is_school_member(uuid) to authenticated;
grant execute on function public.has_school_role(uuid,text[]) to authenticated;

create function public.create_school(p_name text,p_code text default null,p_county text default null) returns uuid language plpgsql security definer set search_path='' as $$
declare sid uuid;
begin
 if auth.uid() is null then raise exception 'Authentication required'; end if;
 if length(trim(coalesce(p_name,''))) not between 1 and 160 then raise exception 'Invalid school name'; end if;
 insert into public.schools(name,school_code,county) values(trim(p_name),nullif(trim(p_code),''),nullif(trim(p_county),'')) returning id into sid;
 insert into public.school_members(school_id,user_id,role) values(sid,auth.uid(),'admin');
 insert into public.profiles(id) values(auth.uid()) on conflict(id) do nothing;
 return sid;
end $$;
revoke all on function public.create_school(text,text,text) from public;
grant execute on function public.create_school(text,text,text) to authenticated;

create function public.add_school_member(p_school uuid,p_email text,p_role text) returns void language plpgsql security definer set search_path='' as $$
declare uid uuid;
begin
 if not public.has_school_role(p_school,array['admin']) then raise exception 'School admin role required'; end if;
 if p_role not in ('admin','bursar','accountant','teacher','exams_officer','viewer') then raise exception 'Invalid role'; end if;
 select id into uid from auth.users where lower(email)=lower(trim(p_email));
 if uid is null then raise exception 'User must register with Supabase Auth first'; end if;
 insert into public.school_members(school_id,user_id,role) values(p_school,uid,p_role) on conflict(school_id,user_id) do update set role=excluded.role;
end $$;
revoke all on function public.add_school_member(uuid,text,text) from public;
grant execute on function public.add_school_member(uuid,text,text) to authenticated;

do $$ declare t text; begin
 foreach t in array array['schools','profiles','school_members','students','fee_accounts','fee_payments','expenses','academic_terms','subjects','assessments','marks','attendance','audit_events'] loop
  execute format('alter table public.%I enable row level security',t);
 end loop;
end $$;

create policy "school members read school" on public.schools for select to authenticated using(public.is_school_member(id));
create policy "school admins update school" on public.schools for update to authenticated using(public.has_school_role(id,array['admin'])) with check(public.has_school_role(id,array['admin']));
create policy "own profile read" on public.profiles for select to authenticated using(id=(select auth.uid()));
create policy "own profile update" on public.profiles for update to authenticated using(id=(select auth.uid())) with check(id=(select auth.uid()));
create policy "members read membership" on public.school_members for select to authenticated using(public.is_school_member(school_id));

create policy "members read students" on public.students for select to authenticated using(public.is_school_member(school_id));
create policy "finance manage students" on public.students for all to authenticated using(public.has_school_role(school_id,array['admin','bursar'])) with check(public.has_school_role(school_id,array['admin','bursar']));
create policy "finance read fee accounts" on public.fee_accounts for select to authenticated using(public.has_school_role(school_id,array['admin','bursar','accountant']));
create policy "finance write fee accounts" on public.fee_accounts for all to authenticated using(public.has_school_role(school_id,array['admin','bursar'])) with check(public.has_school_role(school_id,array['admin','bursar']));
create policy "finance read payments" on public.fee_payments for select to authenticated using(public.has_school_role(school_id,array['admin','bursar','accountant']));
create policy "finance create payments" on public.fee_payments for insert to authenticated with check(public.has_school_role(school_id,array['admin','bursar']));
create policy "admins correct payments" on public.fee_payments for update to authenticated using(public.has_school_role(school_id,array['admin'])) with check(public.has_school_role(school_id,array['admin']));
create policy "finance read expenses" on public.expenses for select to authenticated using(public.has_school_role(school_id,array['admin','bursar','accountant']));
create policy "finance create expenses" on public.expenses for insert to authenticated with check(public.has_school_role(school_id,array['admin','accountant']));
create policy "admins update expenses" on public.expenses for update to authenticated using(public.has_school_role(school_id,array['admin'])) with check(public.has_school_role(school_id,array['admin']));

create policy "members read terms" on public.academic_terms for select to authenticated using(public.is_school_member(school_id));
create policy "academic manage terms" on public.academic_terms for all to authenticated using(public.has_school_role(school_id,array['admin','exams_officer'])) with check(public.has_school_role(school_id,array['admin','exams_officer']));
create policy "members read subjects" on public.subjects for select to authenticated using(public.is_school_member(school_id));
create policy "academic manage subjects" on public.subjects for all to authenticated using(public.has_school_role(school_id,array['admin','exams_officer'])) with check(public.has_school_role(school_id,array['admin','exams_officer']));
create policy "members read assessments" on public.assessments for select to authenticated using(public.is_school_member(school_id));
create policy "academic manage assessments" on public.assessments for all to authenticated using(public.has_school_role(school_id,array['admin','exams_officer'])) with check(public.has_school_role(school_id,array['admin','exams_officer']));
create policy "members read marks" on public.marks for select to authenticated using(public.is_school_member(school_id));
create policy "teachers insert marks" on public.marks for insert to authenticated with check(public.has_school_role(school_id,array['admin','teacher','exams_officer']));
create policy "teachers update marks" on public.marks for update to authenticated using(public.has_school_role(school_id,array['admin','teacher','exams_officer'])) with check(public.has_school_role(school_id,array['admin','teacher','exams_officer']));
create policy "members read attendance" on public.attendance for select to authenticated using(public.is_school_member(school_id));
create policy "teachers insert attendance" on public.attendance for insert to authenticated with check(public.has_school_role(school_id,array['admin','teacher']));
create policy "teachers update attendance" on public.attendance for update to authenticated using(public.has_school_role(school_id,array['admin','teacher'])) with check(public.has_school_role(school_id,array['admin','teacher']));
create policy "admins read audit" on public.audit_events for select to authenticated using(public.has_school_role(school_id,array['admin']));
create policy "members append audit" on public.audit_events for insert to authenticated with check(public.is_school_member(school_id) and actor_id=(select auth.uid()));

create index students_school_class_idx on public.students(school_id,class_name);
create index fee_accounts_student_idx on public.fee_accounts(school_id,student_id);
create index fee_payments_date_idx on public.fee_payments(school_id,paid_at desc);
create index expenses_date_idx on public.expenses(school_id,expense_date desc);
create index marks_assessment_idx on public.marks(school_id,assessment_id);
create index attendance_date_idx on public.attendance(school_id,attendance_date desc);
create index audit_created_idx on public.audit_events(school_id,created_at desc);

do $$ declare t text; begin
 foreach t in array array['students','fee_accounts','fee_payments','expenses','academic_terms','subjects','assessments','marks','attendance'] loop
  begin execute format('alter publication supabase_realtime add table public.%I',t); exception when duplicate_object then null; end;
 end loop;
end $$;
commit;
