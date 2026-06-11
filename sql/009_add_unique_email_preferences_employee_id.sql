-- Deduplicate existing email_preferences rows and enforce one record per employee_id.

DELETE FROM email_preferences a
USING email_preferences b
WHERE a.id > b.id
  AND a.employee_id IS NOT DISTINCT FROM b.employee_id
  AND a.employee_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS idx_email_preferences_employee_id_unique
  ON email_preferences (employee_id)
  WHERE employee_id IS NOT NULL;
