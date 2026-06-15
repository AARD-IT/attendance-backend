-- Add a database-level uniqueness constraint for monthly report email logs
-- Ensures that the same employee cannot receive duplicate monthly report emails with the same subject.

CREATE UNIQUE INDEX IF NOT EXISTS idx_email_logs_monthly_report_unique
  ON email_logs (employee_id, email_type, subject)
  WHERE email_type = 'monthly_report';
