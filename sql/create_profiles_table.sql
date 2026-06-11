-- Phase 1 attendance dashboard schema for Supabase

create table if not exists profiles (
    id uuid primary key references auth.users(id),
    email text unique not null,
    full_name text,
    role text not null check (role in ('CEO','EMPLOYEE')),
    created_at timestamp with time zone default now(),
    updated_at timestamp with time zone default now()
);

-- Example seed rows
insert into profiles (id, email, full_name, role)
values
    ('00000000-0000-4000-8000-000000000001', 'ceo@example.com', 'Attendance CEO', 'CEO'),
    ('00000000-0000-4000-8000-000000000002', 'employee@example.com', 'Attendance Employee', 'EMPLOYEE')
on conflict (id) do nothing;
