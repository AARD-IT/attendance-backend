create table if not exists automation_job_executions (
  id uuid primary key default gen_random_uuid(),
  job_type text not null,
  execution_date date not null,
  status text not null default 'RUNNING',
  last_run_at timestamptz not null default now(),
  details jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint ux_automation_job_executions_job_date unique (job_type, execution_date)
);

create index if not exists idx_automation_job_executions_job_type on automation_job_executions (job_type);
create index if not exists idx_automation_job_executions_execution_date on automation_job_executions (execution_date desc);