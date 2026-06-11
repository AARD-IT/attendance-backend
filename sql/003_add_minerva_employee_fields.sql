-- Add Minerva employee fields to profiles table
-- These columns store additional employee information from Minerva sync

ALTER TABLE profiles ADD COLUMN IF NOT EXISTS first_name text;
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS last_name text;
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS mobile text;
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS department text;
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS position text;
