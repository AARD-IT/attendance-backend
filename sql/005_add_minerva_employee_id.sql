-- Add Minerva employee identifier to profiles for display and analytics
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS minerva_employee_id text;

CREATE INDEX IF NOT EXISTS idx_profiles_minerva_employee_id
    ON profiles (minerva_employee_id);
