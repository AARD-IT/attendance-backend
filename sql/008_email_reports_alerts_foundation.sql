-- Attendance Reports & Alerts database foundation
-- Creates email automation settings, preferences, logs, and templates

CREATE TABLE IF NOT EXISTS email_automation_settings (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  monthly_report_enabled BOOLEAN NOT NULL DEFAULT false,
  monthly_report_day INTEGER NOT NULL DEFAULT 5,
  monthly_report_time TEXT NOT NULL DEFAULT '09:00',
  late_login_enabled BOOLEAN NOT NULL DEFAULT false,
  late_login_delay TEXT NOT NULL DEFAULT 'same_day',
  late_login_time TEXT NOT NULL DEFAULT '18:00',
  early_logout_enabled BOOLEAN NOT NULL DEFAULT false,
  early_logout_delay TEXT NOT NULL DEFAULT 'same_day',
  early_logout_time TEXT NOT NULL DEFAULT '22:30',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS email_preferences (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  employee_id UUID,
  employee_name TEXT,
  employee_email TEXT,
  monthly_report_mode TEXT NOT NULL DEFAULT 'manual' CHECK (monthly_report_mode IN ('manual', 'auto')),
  late_login_mode TEXT NOT NULL DEFAULT 'manual' CHECK (late_login_mode IN ('manual', 'auto')),
  early_logout_mode TEXT NOT NULL DEFAULT 'manual' CHECK (early_logout_mode IN ('manual', 'auto')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS email_logs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  employee_id UUID,
  employee_name TEXT,
  employee_email TEXT,
  cc_email TEXT,
  email_type TEXT,
  subject TEXT,
  email_body TEXT,
  status TEXT CHECK (status IN ('pending', 'sent', 'failed')),
  provider TEXT,
  provider_message_id TEXT,
  sent_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS email_templates (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  template_name TEXT NOT NULL,
  email_subject TEXT,
  email_body TEXT,
  active BOOLEAN NOT NULL DEFAULT true,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_email_preferences_employee_id ON email_preferences (employee_id);
CREATE INDEX IF NOT EXISTS idx_email_logs_employee_id ON email_logs (employee_id);
CREATE INDEX IF NOT EXISTS idx_email_logs_email_type ON email_logs (email_type);
CREATE INDEX IF NOT EXISTS idx_email_logs_status ON email_logs (status);
CREATE INDEX IF NOT EXISTS idx_email_logs_sent_at ON email_logs (sent_at);

ALTER TABLE email_automation_settings ENABLE ROW LEVEL SECURITY;
ALTER TABLE email_preferences ENABLE ROW LEVEL SECURITY;
ALTER TABLE email_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE email_templates ENABLE ROW LEVEL SECURITY;

CREATE POLICY "ceo_full_access_email_automation_settings" ON email_automation_settings
  FOR ALL
  USING (EXISTS (SELECT 1 FROM profiles p WHERE p.id = auth.uid() AND p.role = 'CEO'))
  WITH CHECK (EXISTS (SELECT 1 FROM profiles p WHERE p.id = auth.uid() AND p.role = 'CEO'));

CREATE POLICY "service_role_manage_email_automation_settings" ON email_automation_settings
  FOR ALL
  USING (auth.jwt() ->> 'role' = 'service_role')
  WITH CHECK (auth.jwt() ->> 'role' = 'service_role');

CREATE POLICY "ceo_full_access_email_preferences" ON email_preferences
  FOR ALL
  USING (EXISTS (SELECT 1 FROM profiles p WHERE p.id = auth.uid() AND p.role = 'CEO'))
  WITH CHECK (EXISTS (SELECT 1 FROM profiles p WHERE p.id = auth.uid() AND p.role = 'CEO'));

CREATE POLICY "service_role_manage_email_preferences" ON email_preferences
  FOR ALL
  USING (auth.jwt() ->> 'role' = 'service_role')
  WITH CHECK (auth.jwt() ->> 'role' = 'service_role');

CREATE POLICY "ceo_full_access_email_logs" ON email_logs
  FOR ALL
  USING (EXISTS (SELECT 1 FROM profiles p WHERE p.id = auth.uid() AND p.role = 'CEO'))
  WITH CHECK (EXISTS (SELECT 1 FROM profiles p WHERE p.id = auth.uid() AND p.role = 'CEO'));

CREATE POLICY "service_role_manage_email_logs" ON email_logs
  FOR ALL
  USING (auth.jwt() ->> 'role' = 'service_role')
  WITH CHECK (auth.jwt() ->> 'role' = 'service_role');

CREATE POLICY "ceo_full_access_email_templates" ON email_templates
  FOR ALL
  USING (EXISTS (SELECT 1 FROM profiles p WHERE p.id = auth.uid() AND p.role = 'CEO'))
  WITH CHECK (EXISTS (SELECT 1 FROM profiles p WHERE p.id = auth.uid() AND p.role = 'CEO'));

CREATE POLICY "service_role_manage_email_templates" ON email_templates
  FOR ALL
  USING (auth.jwt() ->> 'role' = 'service_role')
  WITH CHECK (auth.jwt() ->> 'role' = 'service_role');

INSERT INTO email_automation_settings (
  monthly_report_enabled,
  monthly_report_day,
  monthly_report_time,
  late_login_enabled,
  late_login_delay,
  late_login_time,
  early_logout_enabled,
  early_logout_delay,
  early_logout_time
)
VALUES (false, 5, '09:00', false, 'same_day', '18:00', false, 'same_day', '22:30');

INSERT INTO email_templates (template_name, email_subject, email_body, active)
VALUES
  ('monthly_report', 'Monthly Attendance Report', 'Monthly attendance report preview will be delivered here.', true),
  ('late_login', 'Late Login Alert', 'Late login alert preview will be delivered here.', true),
  ('early_logout', 'Early Logout Alert', 'Early logout alert preview will be delivered here.', true),
  ('missing_punch', 'Missing Punch Alert', 'Missing punch alert preview will be delivered here.', true),
  ('shift_assignment', 'Shift Assignment Notification', 'Shift assignment notification preview will be delivered here.', true);
