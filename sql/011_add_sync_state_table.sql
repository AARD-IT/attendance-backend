create table if not exists minerva_sync_state (
  id text primary key,
  last_sync_at timestamptz null,
  records_synced integer default 0,
  status text default 'OK',
  updated_at timestamptz default now()
);
