CREATE TABLE IF NOT EXISTS employee_shift_assignments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    employee_id TEXT NOT NULL,
    minerva_employee_id TEXT,
    employee_name TEXT,
    employee_email TEXT,
    cc_email TEXT,
    shift_type TEXT NOT NULL,
    effective_from DATE NOT NULL,
    effective_to DATE NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_employee_shift_assignments_employee_id ON employee_shift_assignments (employee_id);
CREATE INDEX IF NOT EXISTS idx_employee_shift_assignments_dates ON employee_shift_assignments (effective_from, effective_to, is_active);
