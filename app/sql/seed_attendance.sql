-- Seed profiles (5 employees) and 30 attendance records
insert into profiles (id, email, full_name, role)
values
  ('11111111-0000-4000-8000-000000000001','ceo@example.com','Attendance CEO','CEO'),
  ('22222222-0000-4000-8000-000000000002','emp1@example.com','Employee One','EMPLOYEE'),
  ('22222222-0000-4000-8000-000000000003','emp2@example.com','Employee Two','EMPLOYEE'),
  ('22222222-0000-4000-8000-000000000004','emp3@example.com','Employee Three','EMPLOYEE'),
  ('22222222-0000-4000-8000-000000000005','emp4@example.com','Employee Four','EMPLOYEE')
on conflict (id) do nothing;

-- Sample attendance records (30 rows over the last 10 days)
insert into attendance_records (employee_id, attendance_date, first_punch, last_punch, total_hours, status)
values
  ('22222222-0000-4000-8000-000000000002', current_date - 1, now() - interval '9 hours', now() - interval '1 hour', 8.00, 'PRESENT'),
  ('22222222-0000-4000-8000-000000000003', current_date - 1, null, null, 0, 'ABSENT'),
  ('22222222-0000-4000-8000-000000000004', current_date - 1, now() - interval '8 hours', now() - interval '4 hours', 4.00, 'HALF_DAY'),
  ('22222222-0000-4000-8000-000000000005', current_date - 1, null, null, 0, 'LEAVE'),
  ('22222222-0000-4000-8000-000000000002', current_date - 2, now() - interval '9 hours', now() - interval '1 hour', 8.00, 'PRESENT'),
  ('22222222-0000-4000-8000-000000000003', current_date - 2, now() - interval '9 hours', now() - interval '2 hour', 7.00, 'PRESENT'),
  ('22222222-0000-4000-8000-000000000004', current_date - 2, null, null, 0, 'ABSENT'),
  ('22222222-0000-4000-8000-000000000005', current_date - 2, now() - interval '9 hours', now() - interval '1 hour', 8.00, 'PRESENT'),
  ('22222222-0000-4000-8000-000000000002', current_date - 3, now() - interval '8 hours', now() - interval '2 hour', 6.00, 'HALF_DAY'),
  ('22222222-0000-4000-8000-000000000003', current_date - 3, null, null, 0, 'LEAVE'),
  ('22222222-0000-4000-8000-000000000004', current_date - 3, now() - interval '9 hours', now() - interval '1 hour', 8.00, 'PRESENT'),
  ('22222222-0000-4000-8000-000000000005', current_date - 3, now() - interval '9 hours', now() - interval '1 hour', 8.00, 'PRESENT'),
  ('22222222-0000-4000-8000-000000000002', current_date - 4, null, null, 0, 'ABSENT'),
  ('22222222-0000-4000-8000-000000000003', current_date - 4, now() - interval '9 hours', now() - interval '1 hour', 8.00, 'PRESENT'),
  ('22222222-0000-4000-8000-000000000004', current_date - 4, now() - interval '8 hours', now() - interval '4 hours', 4.00, 'HALF_DAY'),
  ('22222222-0000-4000-8000-000000000005', current_date - 4, null, null, 0, 'LEAVE'),
  ('22222222-0000-4000-8000-000000000002', current_date - 5, now() - interval '9 hours', now() - interval '1 hour', 8.00, 'PRESENT'),
  ('22222222-0000-4000-8000-000000000003', current_date - 5, now() - interval '9 hours', now() - interval '1 hour', 8.00, 'PRESENT'),
  ('22222222-0000-4000-8000-000000000004', current_date - 5, null, null, 0, 'ABSENT'),
  ('22222222-0000-4000-8000-000000000005', current_date - 5, now() - interval '8 hours', now() - interval '2 hours', 6.00, 'HALF_DAY'),
  ('22222222-0000-4000-8000-000000000002', current_date, now() - interval '8 hours', now() - interval '1 hour', 7.00, 'PRESENT'),
  ('22222222-0000-4000-8000-000000000003', current_date, null, null, 0, 'ABSENT'),
  ('22222222-0000-4000-8000-000000000004', current_date, now() - interval '9 hours', now() - interval '2 hours', 7.00, 'PRESENT'),
  ('22222222-0000-4000-8000-000000000005', current_date, null, null, 0, 'LEAVE'),
  ('22222222-0000-4000-8000-000000000002', current_date - 6, now() - interval '9 hours', now() - interval '1 hour', 8.00, 'PRESENT'),
  ('22222222-0000-4000-8000-000000000003', current_date - 6, now() - interval '9 hours', now() - interval '1 hour', 8.00, 'PRESENT'),
  ('22222222-0000-4000-8000-000000000004', current_date - 6, now() - interval '8 hours', now() - interval '4 hours', 4.00, 'HALF_DAY'),
  ('22222222-0000-4000-8000-000000000005', current_date - 6, now() - interval '9 hours', now() - interval '1 hour', 8.00, 'PRESENT')
on conflict do nothing;
