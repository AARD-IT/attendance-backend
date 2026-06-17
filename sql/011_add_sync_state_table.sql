create table if not exists minerva_sync_state (
  id text primary key,
  last_sync_at timestamptz null,
  records_synced integer default 0,
  status text,
  updated_at timestamptz default now()
);

insert into minerva_sync_state (
  id,
  last_sync_at,
  records_synced,
  status
)
values (
  'global',
  null,
  0,
  'INITIAL'
)
on conflict (id) do nothing;
