-- Dynamic shift master, assignment history, and notification settings foundation

CREATE TABLE IF NOT EXISTS shifts (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  shift_name VARCHAR(100) NOT NULL UNIQUE,
  start_time TIME NOT NULL,
  end_time TIME NOT NULL,
  grace_time_minutes INTEGER NOT NULL DEFAULT 15,
  minimum_working_hours NUMERIC(4, 2) NOT NULL DEFAULT 8,
  login_deviation_minutes INTEGER NOT NULL DEFAULT 15,
  logout_deviation_minutes INTEGER NOT NULL DEFAULT 30,
  status BOOLEAN NOT NULL DEFAULT TRUE,
  created_by UUID,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_shifts_status ON shifts (status);
CREATE INDEX IF NOT EXISTS idx_shifts_shift_name ON shifts (shift_name);

-- Seed legacy shift definitions (matches prior hardcoded cutoffs)
INSERT INTO shifts (
  shift_name,
  start_time,
  end_time,
  grace_time_minutes,
  minimum_working_hours,
  login_deviation_minutes,
  logout_deviation_minutes,
  status
)
VALUES
  ('Shift 1', '10:20:00', '18:00:00', 15, 8, 15, 0, TRUE),
  ('Shift 2', '14:20:00', '22:00:00', 15, 8, 15, 0, TRUE)
ON CONFLICT (shift_name) DO NOTHING;

ALTER TABLE employee_shift_assignments
  ADD COLUMN IF NOT EXISTS shift_id UUID REFERENCES shifts(id),
  ADD COLUMN IF NOT EXISTS start_date DATE,
  ADD COLUMN IF NOT EXISTS end_date DATE,
  ADD COLUMN IF NOT EXISTS assigned_by UUID,
  ADD COLUMN IF NOT EXISTS status BOOLEAN DEFAULT TRUE;

UPDATE employee_shift_assignments
SET
  start_date = COALESCE(start_date, effective_from),
  end_date = COALESCE(end_date, effective_to),
  status = COALESCE(status, is_active, TRUE)
WHERE start_date IS NULL OR end_date IS NULL OR status IS NULL;

UPDATE employee_shift_assignments esa
SET shift_id = s.id
FROM shifts s
WHERE esa.shift_id IS NULL
  AND LOWER(TRIM(COALESCE(esa.shift_type, ''))) = LOWER(TRIM(s.shift_name));

ALTER TABLE shift_assignments
  ADD COLUMN IF NOT EXISTS shift_id UUID REFERENCES shifts(id),
  ADD COLUMN IF NOT EXISTS start_date DATE,
  ADD COLUMN IF NOT EXISTS end_date DATE,
  ADD COLUMN IF NOT EXISTS status BOOLEAN DEFAULT TRUE;

UPDATE shift_assignments
SET
  start_date = COALESCE(start_date, effective_from),
  end_date = COALESCE(end_date, effective_to),
  status = COALESCE(status, is_active, TRUE)
WHERE start_date IS NULL OR end_date IS NULL OR status IS NULL;

UPDATE shift_assignments sa
SET shift_id = s.id
FROM shifts s
WHERE sa.shift_id IS NULL
  AND LOWER(TRIM(COALESCE(sa.shift_type, ''))) = LOWER(TRIM(s.shift_name));

CREATE TABLE IF NOT EXISTS shift_assignment_history (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  employee_id UUID,
  old_shift_id UUID REFERENCES shifts(id),
  new_shift_id UUID REFERENCES shifts(id),
  effective_date DATE NOT NULL,
  changed_by UUID,
  changed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  reason TEXT
);

CREATE INDEX IF NOT EXISTS idx_shift_assignment_history_employee_id ON shift_assignment_history (employee_id);
CREATE INDEX IF NOT EXISTS idx_shift_assignment_history_effective_date ON shift_assignment_history (effective_date);
CREATE INDEX IF NOT EXISTS idx_shift_assignment_history_new_shift_id ON shift_assignment_history (new_shift_id);

CREATE TABLE IF NOT EXISTS employee_notification_settings (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  employee_id UUID NOT NULL,
  employee_email TEXT,
  cc_email TEXT,
  monthly_report_mode TEXT NOT NULL DEFAULT 'MANUAL' CHECK (monthly_report_mode IN ('MANUAL', 'AUTOMATIC')),
  late_login_mode TEXT NOT NULL DEFAULT 'MANUAL' CHECK (late_login_mode IN ('MANUAL', 'AUTOMATIC')),
  early_logout_mode TEXT NOT NULL DEFAULT 'MANUAL' CHECK (early_logout_mode IN ('MANUAL', 'AUTOMATIC')),
  missing_punch_mode TEXT NOT NULL DEFAULT 'MANUAL' CHECK (missing_punch_mode IN ('MANUAL', 'AUTOMATIC')),
  escalation_mode TEXT NOT NULL DEFAULT 'MANUAL' CHECK (escalation_mode IN ('MANUAL', 'AUTOMATIC')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_employee_notification_settings_employee_id
  ON employee_notification_settings (employee_id);

INSERT INTO employee_notification_settings (
  employee_id,
  employee_email,
  cc_email,
  monthly_report_mode,
  late_login_mode,
  early_logout_mode,
  missing_punch_mode,
  escalation_mode
)
SELECT
  ep.employee_id,
  ep.employee_email,
  NULL,
  CASE WHEN LOWER(ep.monthly_report_mode) = 'auto' THEN 'AUTOMATIC' ELSE 'MANUAL' END,
  CASE WHEN LOWER(ep.late_login_mode) = 'auto' THEN 'AUTOMATIC' ELSE 'MANUAL' END,
  CASE WHEN LOWER(ep.early_logout_mode) = 'auto' THEN 'AUTOMATIC' ELSE 'MANUAL' END,
  'MANUAL',
  'MANUAL'
FROM email_preferences ep
WHERE ep.employee_id IS NOT NULL
ON CONFLICT (employee_id) DO NOTHING;

ALTER TABLE email_automation_settings
  ADD COLUMN IF NOT EXISTS monthly_report_cc_enabled BOOLEAN NOT NULL DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS monthly_report_template_id UUID,
  ADD COLUMN IF NOT EXISTS late_login_send_immediately BOOLEAN NOT NULL DEFAULT TRUE,
  ADD COLUMN IF NOT EXISTS late_login_delay_minutes INTEGER NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS late_login_template_id UUID,
  ADD COLUMN IF NOT EXISTS early_logout_delay_minutes INTEGER NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS early_logout_template_id UUID,
  ADD COLUMN IF NOT EXISTS missing_punch_enabled BOOLEAN NOT NULL DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS missing_punch_delay_minutes INTEGER NOT NULL DEFAULT 60,
  ADD COLUMN IF NOT EXISTS missing_punch_template_id UUID,
  ADD COLUMN IF NOT EXISTS escalation_enabled BOOLEAN NOT NULL DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS escalation_late_threshold INTEGER NOT NULL DEFAULT 5,
  ADD COLUMN IF NOT EXISTS escalation_deviation_threshold INTEGER NOT NULL DEFAULT 5,
  ADD COLUMN IF NOT EXISTS escalation_recipients TEXT,
  ADD COLUMN IF NOT EXISTS escalation_template_id UUID;

ALTER TABLE email_logs
  ADD COLUMN IF NOT EXISTS source TEXT DEFAULT 'AUTOMATION' CHECK (source IN ('AUTOMATION', 'MANUAL')),
  ADD COLUMN IF NOT EXISTS sent_by UUID,
  ADD COLUMN IF NOT EXISTS delivery_status TEXT;

CREATE INDEX IF NOT EXISTS idx_email_logs_source ON email_logs (source);
CREATE INDEX IF NOT EXISTS idx_email_logs_sent_by ON email_logs (sent_by);

ALTER TABLE shifts ENABLE ROW LEVEL SECURITY;
ALTER TABLE shift_assignment_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE employee_notification_settings ENABLE ROW LEVEL SECURITY;

CREATE POLICY "ceo_full_access_shifts" ON shifts
  FOR ALL
  USING (EXISTS (SELECT 1 FROM profiles p WHERE p.id = auth.uid() AND p.role = 'CEO'))
  WITH CHECK (EXISTS (SELECT 1 FROM profiles p WHERE p.id = auth.uid() AND p.role = 'CEO'));

CREATE POLICY "service_role_manage_shifts" ON shifts
  FOR ALL
  USING (auth.jwt() ->> 'role' = 'service_role')
  WITH CHECK (auth.jwt() ->> 'role' = 'service_role');

CREATE POLICY "ceo_full_access_shift_assignment_history" ON shift_assignment_history
  FOR ALL
  USING (EXISTS (SELECT 1 FROM profiles p WHERE p.id = auth.uid() AND p.role = 'CEO'))
  WITH CHECK (EXISTS (SELECT 1 FROM profiles p WHERE p.id = auth.uid() AND p.role = 'CEO'));

CREATE POLICY "service_role_manage_shift_assignment_history" ON shift_assignment_history
  FOR ALL
  USING (auth.jwt() ->> 'role' = 'service_role')
  WITH CHECK (auth.jwt() ->> 'role' = 'service_role');

CREATE POLICY "ceo_full_access_employee_notification_settings" ON employee_notification_settings
  FOR ALL
  USING (EXISTS (SELECT 1 FROM profiles p WHERE p.id = auth.uid() AND p.role = 'CEO'))
  WITH CHECK (EXISTS (SELECT 1 FROM profiles p WHERE p.id = auth.uid() AND p.role = 'CEO'));

CREATE POLICY "service_role_manage_employee_notification_settings" ON employee_notification_settings
  FOR ALL
  USING (auth.jwt() ->> 'role' = 'service_role')
  WITH CHECK (auth.jwt() ->> 'role' = 'service_role');
