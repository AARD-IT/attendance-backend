-- Expand the processed attendance table to store the fields used by dashboards and alerts.
-- Also normalize CEO dashboard settings back to a single shared global row.

alter table attendance_daily
  add column if not exists employee_name text,
  add column if not exists first_in timestamptz,
  add column if not exists last_out timestamptz,
  add column if not exists shift text,
  add column if not exists late_login_flag boolean not null default false,
  add column if not exists early_logout_flag boolean not null default false;

update attendance_daily ad
set
  employee_name = coalesce(
    ad.employee_name,
    p.full_name,
    nullif(trim(concat_ws(' ', p.first_name, p.last_name)), '')
  ),
  first_in = coalesce(ad.first_in, ad.first_punch),
  last_out = coalesce(ad.last_out, ad.last_punch),
  shift = coalesce(ad.shift, 'Shift 1'),
  late_login_flag = coalesce(ad.late_login_flag, false),
  early_logout_flag = coalesce(ad.early_logout_flag, false)
from profiles p
where p.id = ad.employee_id;

insert into ceo_dashboard_settings (id, auto_refresh_enabled, last_loaded_at, last_loaded_by)
values ('global', false, null, null)
on conflict (id) do nothing;

delete from ceo_dashboard_settings
where id <> 'global' and id like 'ceo:%';
