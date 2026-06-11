CREATE TABLE IF NOT EXISTS shift_assignments (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  employee_id TEXT,
  employee_name TEXT,
  employee_email TEXT,
  cc_email TEXT,
  shift_type TEXT NOT NULL DEFAULT 'Shift 1',
  effective_from DATE NOT NULL,
  effective_to DATE NOT NULL,
  is_active BOOLEAN DEFAULT TRUE,
  assigned_by UUID,
  assigned_at TIMESTAMPTZ DEFAULT NOW(),
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_shift_assignments_employee_id ON shift_assignments (employee_id);
CREATE INDEX IF NOT EXISTS idx_shift_assignments_dates ON shift_assignments (effective_from, effective_to, is_active);
