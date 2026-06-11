-- Remove foreign key constraint from profiles.id
-- This allows profiles to exist independently without auth.users entries
-- Needed for Minerva employee sync which creates profiles without creating auth users

ALTER TABLE profiles DROP CONSTRAINT IF EXISTS profiles_id_fkey;

-- profiles.id remains as UUID PRIMARY KEY but is no longer linked to auth.users
-- This enables:
-- 1. Creating profiles from Minerva employees without auth accounts
-- 2. Later linking profiles to auth users when they sign up
