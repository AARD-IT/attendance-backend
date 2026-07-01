-- Migration: Create sync_status and kpi_cache tables
-- Add support for background sync logs and cached metrics dashboard

CREATE TABLE IF NOT EXISTS sync_status (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  last_successful_sync timestamptz NULL,
  last_attempt timestamptz NULL,
  status text NOT NULL, -- 'SUCCESS', 'FAILED', 'RUNNING'
  records_processed integer DEFAULT 0,
  employees_synced integer DEFAULT 0,
  attendance_synced integer DEFAULT 0,
  duration_ms integer DEFAULT 0,
  error_message text NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_sync_status_status ON sync_status (status);
CREATE INDEX IF NOT EXISTS idx_sync_status_created_at ON sync_status (created_at DESC);

CREATE TABLE IF NOT EXISTS kpi_cache (
  id text PRIMARY KEY, -- 'global'
  total_employees integer DEFAULT 0,
  present_today integer DEFAULT 0,
  absent_today integer DEFAULT 0,
  late_arrivals integer DEFAULT 0,
  early_logout integer DEFAULT 0,
  attendance_percentage numeric DEFAULT 0.0,
  active_employees integer DEFAULT 0,
  live_attendance_count integer DEFAULT 0,
  updated_at timestamptz NOT NULL DEFAULT now()
);

-- Insert standard global cached row
INSERT INTO kpi_cache (id) VALUES ('global') ON CONFLICT (id) DO NOTHING;
