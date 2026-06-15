-- Two-layer Minerva attendance architecture

create table if not exists minerva_raw_logs (
  id uuid primary key default gen_random_uuid(),
  employee_id uuid null,
  employee_code text null,
  timestamp timestamptz not null,
  raw_payload jsonb not null default '{}'::jsonb,
  created_at timestamptz default now()
);

create index if not exists idx_minerva_raw_logs_employee_code on minerva_raw_logs (employee_code);
create index if not exists idx_minerva_raw_logs_timestamp on minerva_raw_logs (timestamp desc);

create table if not exists attendance_daily (
  id uuid primary key default gen_random_uuid(),
  employee_id uuid not null,
  attendance_date date not null,
  first_punch timestamptz null,
  last_punch timestamptz null,
  working_hours numeric(6,2) default 0,
  attendance_status text not null default 'ABSENT',
  created_at timestamptz default now(),
  updated_at timestamptz default now(),
  constraint ux_attendance_daily_employee_date unique (employee_id, attendance_date)
);

create index if not exists idx_attendance_daily_employee on attendance_daily (employee_id);
create index if not exists idx_attendance_daily_date on attendance_daily (attendance_date desc);
