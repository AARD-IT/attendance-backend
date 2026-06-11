-- Attendance records table for Phase 2

create table if not exists attendance_records (
  id uuid primary key default gen_random_uuid(),
  employee_id uuid not null references profiles(id) on delete cascade,
  attendance_date date not null,
  first_punch timestamp with time zone null,
  last_punch timestamp with time zone null,
  total_hours numeric(5,2) default 0,
  status text not null check (status in ('PRESENT','ABSENT','HALF_DAY','LEAVE')),
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

-- One record per employee per date
create unique index if not exists ux_attendance_employee_date on attendance_records (employee_id, attendance_date);

-- Indexes for queries
create index if not exists idx_attendance_employee_id on attendance_records (employee_id);
create index if not exists idx_attendance_date on attendance_records (attendance_date);
