-- Cleanup migration for stale attendance sync data
-- Run this before rebuilding attendance from Minerva.

DELETE FROM attendance_records;
