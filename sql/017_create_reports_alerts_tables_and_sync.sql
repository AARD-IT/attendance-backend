-- Migration 017: Create reports and alerts tables and bidirectional sync triggers
CREATE TABLE IF NOT EXISTS automation_settings (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  monthly_enabled BOOLEAN NOT NULL DEFAULT false,
  monthly_generation_day INTEGER NOT NULL DEFAULT 5,
  monthly_delivery_time TEXT NOT NULL DEFAULT '09:00',
  late_enabled BOOLEAN NOT NULL DEFAULT false,
  late_alert_timing TEXT NOT NULL DEFAULT 'same_day',
  late_delivery_time TEXT NOT NULL DEFAULT '11:00',
  early_enabled BOOLEAN NOT NULL DEFAULT false,
  early_alert_timing TEXT NOT NULL DEFAULT 'same_day',
  early_delivery_time TEXT NOT NULL DEFAULT '22:30',
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS employee_communication_settings (
  employee_id UUID PRIMARY KEY,
  monthly_mode TEXT NOT NULL DEFAULT 'manual' CHECK (monthly_mode IN ('manual', 'auto')),
  late_mode TEXT NOT NULL DEFAULT 'manual' CHECK (late_mode IN ('manual', 'auto')),
  early_mode TEXT NOT NULL DEFAULT 'manual' CHECK (early_mode IN ('manual', 'auto')),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS email_activity_log (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  employee_id UUID,
  email_type TEXT NOT NULL,
  recipient TEXT NOT NULL,
  cc TEXT,
  status TEXT NOT NULL CHECK (status IN ('SENT', 'PENDING', 'FAILED', 'RETRYING')),
  triggered_by TEXT NOT NULL CHECK (triggered_by IN ('MANUAL', 'AUTOMATION')),
  sent_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  error_message TEXT
);

-- Policies for Row Level Security (RLS) to allow CEO full access
ALTER TABLE automation_settings ENABLE ROW LEVEL SECURITY;
ALTER TABLE employee_communication_settings ENABLE ROW LEVEL SECURITY;
ALTER TABLE email_activity_log ENABLE ROW LEVEL SECURITY;

CREATE POLICY "ceo_full_access_automation_settings" ON automation_settings
  FOR ALL
  USING (EXISTS (SELECT 1 FROM profiles p WHERE p.id = auth.uid() AND p.role = 'CEO'))
  WITH CHECK (EXISTS (SELECT 1 FROM profiles p WHERE p.id = auth.uid() AND p.role = 'CEO'));

CREATE POLICY "service_role_manage_automation_settings" ON automation_settings
  FOR ALL
  USING (auth.jwt() ->> 'role' = 'service_role')
  WITH CHECK (auth.jwt() ->> 'role' = 'service_role');

CREATE POLICY "ceo_full_access_employee_communication_settings" ON employee_communication_settings
  FOR ALL
  USING (EXISTS (SELECT 1 FROM profiles p WHERE p.id = auth.uid() AND p.role = 'CEO'))
  WITH CHECK (EXISTS (SELECT 1 FROM profiles p WHERE p.id = auth.uid() AND p.role = 'CEO'));

CREATE POLICY "service_role_manage_employee_communication_settings" ON employee_communication_settings
  FOR ALL
  USING (auth.jwt() ->> 'role' = 'service_role')
  WITH CHECK (auth.jwt() ->> 'role' = 'service_role');

CREATE POLICY "ceo_full_access_email_activity_log" ON email_activity_log
  FOR ALL
  USING (EXISTS (SELECT 1 FROM profiles p WHERE p.id = auth.uid() AND p.role = 'CEO'))
  WITH CHECK (EXISTS (SELECT 1 FROM profiles p WHERE p.id = auth.uid() AND p.role = 'CEO'));

CREATE POLICY "service_role_manage_email_activity_log" ON email_activity_log
  FOR ALL
  USING (auth.jwt() ->> 'role' = 'service_role')
  WITH CHECK (auth.jwt() ->> 'role' = 'service_role');

-- Insert initial values for automation_settings if empty
INSERT INTO automation_settings (id, monthly_enabled, monthly_generation_day, monthly_delivery_time, late_enabled, late_alert_timing, late_delivery_time, early_enabled, early_alert_timing, early_delivery_time)
VALUES ('00000000-0000-0000-0000-000000000001', false, 5, '09:00', false, 'same_day', '11:00', false, 'same_day', '22:30')
ON CONFLICT (id) DO NOTHING;

-- Bidirectional Sync Triggers to keep legacy tables synchronized
-- 1. sync between email_automation_settings and automation_settings
CREATE OR REPLACE FUNCTION sync_legacy_to_new_automation_settings()
RETURNS TRIGGER AS $$
BEGIN
  IF pg_trigger_depth() > 1 THEN
    RETURN NEW;
  END IF;
  
  INSERT INTO automation_settings (
    id,
    monthly_enabled,
    monthly_generation_day,
    monthly_delivery_time,
    late_enabled,
    late_alert_timing,
    late_delivery_time,
    early_enabled,
    early_alert_timing,
    early_delivery_time,
    updated_at
  ) VALUES (
    NEW.id,
    NEW.monthly_report_enabled,
    NEW.monthly_report_day,
    NEW.monthly_report_time,
    NEW.late_login_enabled,
    NEW.late_login_delay,
    NEW.late_login_time,
    NEW.early_logout_enabled,
    NEW.early_logout_delay,
    NEW.early_logout_time,
    NEW.updated_at
  )
  ON CONFLICT (id) DO UPDATE SET
    monthly_enabled = EXCLUDED.monthly_enabled,
    monthly_generation_day = EXCLUDED.monthly_generation_day,
    monthly_delivery_time = EXCLUDED.monthly_delivery_time,
    late_enabled = EXCLUDED.late_enabled,
    late_alert_timing = EXCLUDED.late_alert_timing,
    late_delivery_time = EXCLUDED.late_delivery_time,
    early_enabled = EXCLUDED.early_enabled,
    early_alert_timing = EXCLUDED.early_alert_timing,
    early_delivery_time = EXCLUDED.early_delivery_time,
    updated_at = EXCLUDED.updated_at;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_sync_legacy_to_new_automation_settings
AFTER INSERT OR UPDATE ON email_automation_settings
FOR EACH ROW EXECUTE FUNCTION sync_legacy_to_new_automation_settings();

CREATE OR REPLACE FUNCTION sync_new_to_legacy_automation_settings()
RETURNS TRIGGER AS $$
BEGIN
  IF pg_trigger_depth() > 1 THEN
    RETURN NEW;
  END IF;
  
  INSERT INTO email_automation_settings (
    id,
    monthly_report_enabled,
    monthly_report_day,
    monthly_report_time,
    late_login_enabled,
    late_login_delay,
    late_login_time,
    early_logout_enabled,
    early_logout_delay,
    early_logout_time,
    updated_at
  ) VALUES (
    NEW.id,
    NEW.monthly_enabled,
    NEW.monthly_generation_day,
    NEW.monthly_delivery_time,
    NEW.late_enabled,
    NEW.late_alert_timing,
    NEW.late_delivery_time,
    NEW.early_enabled,
    NEW.early_alert_timing,
    NEW.early_delivery_time,
    NEW.updated_at
  )
  ON CONFLICT (id) DO UPDATE SET
    monthly_report_enabled = EXCLUDED.monthly_report_enabled,
    monthly_report_day = EXCLUDED.monthly_report_day,
    monthly_report_time = EXCLUDED.monthly_report_time,
    late_login_enabled = EXCLUDED.late_login_enabled,
    late_login_delay = EXCLUDED.late_login_delay,
    late_login_time = EXCLUDED.late_login_time,
    early_logout_enabled = EXCLUDED.early_logout_enabled,
    early_logout_delay = EXCLUDED.early_logout_delay,
    early_logout_time = EXCLUDED.early_logout_time,
    updated_at = EXCLUDED.updated_at;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_sync_new_to_legacy_automation_settings
AFTER INSERT OR UPDATE ON automation_settings
FOR EACH ROW EXECUTE FUNCTION sync_new_to_legacy_automation_settings();

-- 2. sync between email_preferences and employee_communication_settings
CREATE OR REPLACE FUNCTION sync_legacy_to_new_email_preferences()
RETURNS TRIGGER AS $$
BEGIN
  IF pg_trigger_depth() > 1 THEN
    RETURN NEW;
  END IF;
  
  IF NEW.employee_id IS NULL THEN
    RETURN NEW;
  END IF;

  INSERT INTO employee_communication_settings (
    employee_id,
    monthly_mode,
    late_mode,
    early_mode,
    updated_at
  ) VALUES (
    NEW.employee_id,
    NEW.monthly_report_mode,
    NEW.late_login_mode,
    NEW.early_logout_mode,
    NEW.updated_at
  )
  ON CONFLICT (employee_id) DO UPDATE SET
    monthly_mode = EXCLUDED.monthly_mode,
    late_mode = EXCLUDED.late_mode,
    early_mode = EXCLUDED.early_mode,
    updated_at = EXCLUDED.updated_at;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_sync_legacy_to_new_email_preferences
AFTER INSERT OR UPDATE ON email_preferences
FOR EACH ROW EXECUTE FUNCTION sync_legacy_to_new_email_preferences();

CREATE OR REPLACE FUNCTION sync_new_to_legacy_email_preferences()
RETURNS TRIGGER AS $$
BEGIN
  IF pg_trigger_depth() > 1 THEN
    RETURN NEW;
  END IF;

  INSERT INTO email_preferences (
    employee_id,
    monthly_report_mode,
    late_login_mode,
    early_logout_mode,
    updated_at
  ) VALUES (
    NEW.employee_id,
    NEW.monthly_mode,
    NEW.late_mode,
    NEW.early_mode,
    NEW.updated_at
  )
  ON CONFLICT (employee_id) DO UPDATE SET
    monthly_report_mode = EXCLUDED.monthly_report_mode,
    late_login_mode = EXCLUDED.late_login_mode,
    early_logout_mode = EXCLUDED.early_logout_mode,
    updated_at = EXCLUDED.updated_at;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_sync_new_to_legacy_email_preferences
AFTER INSERT OR UPDATE ON employee_communication_settings
FOR EACH ROW EXECUTE FUNCTION sync_new_to_legacy_email_preferences();

-- 3. sync from email_logs to email_activity_log
CREATE OR REPLACE FUNCTION sync_legacy_to_new_email_logs()
RETURNS TRIGGER AS $$
BEGIN
  IF pg_trigger_depth() > 1 THEN
    RETURN NEW;
  END IF;

  INSERT INTO email_activity_log (
    id,
    employee_id,
    email_type,
    recipient,
    cc,
    status,
    triggered_by,
    sent_at,
    error_message
  ) VALUES (
    NEW.id,
    NEW.employee_id,
    COALESCE(NEW.email_type, 'unknown'),
    COALESCE(NEW.employee_email, 'unknown@company.com'),
    NEW.cc_email,
    UPPER(COALESCE(NEW.status, 'SENT')),
    COALESCE(UPPER(NEW.provider), 'AUTOMATION'),
    COALESCE(NEW.sent_at, NEW.created_at, now()),
    NULL
  )
  ON CONFLICT (id) DO UPDATE SET
    employee_id = EXCLUDED.employee_id,
    email_type = EXCLUDED.email_type,
    recipient = EXCLUDED.recipient,
    cc = EXCLUDED.cc,
    status = EXCLUDED.status,
    triggered_by = EXCLUDED.triggered_by,
    sent_at = EXCLUDED.sent_at;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_sync_legacy_to_new_email_logs
AFTER INSERT OR UPDATE ON email_logs
FOR EACH ROW EXECUTE FUNCTION sync_legacy_to_new_email_logs();

-- Sync existing legacy records to new tables
INSERT INTO automation_settings (id, monthly_enabled, monthly_generation_day, monthly_delivery_time, late_enabled, late_alert_timing, late_delivery_time, early_enabled, early_alert_timing, early_delivery_time, updated_at)
SELECT id, monthly_report_enabled, monthly_report_day, monthly_report_time, late_login_enabled, late_login_delay, late_login_time, early_logout_enabled, early_logout_delay, early_logout_time, updated_at
FROM email_automation_settings
ON CONFLICT (id) DO NOTHING;

INSERT INTO employee_communication_settings (employee_id, monthly_mode, late_mode, early_mode, updated_at)
SELECT employee_id, monthly_report_mode, late_login_mode, early_logout_mode, updated_at
FROM email_preferences
WHERE employee_id IS NOT NULL
ON CONFLICT (employee_id) DO NOTHING;

INSERT INTO email_activity_log (id, employee_id, email_type, recipient, cc, status, triggered_by, sent_at)
SELECT id, employee_id, COALESCE(email_type, 'unknown'), COALESCE(employee_email, 'unknown@company.com'), cc_email, UPPER(COALESCE(status, 'SENT')), COALESCE(UPPER(provider), 'AUTOMATION'), COALESCE(sent_at, created_at, now())
FROM email_logs
ON CONFLICT (id) DO NOTHING;
