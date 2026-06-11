# Attendance Dashboard Performance Optimization Report

## 1) Refresh warning source

- File: [src/pages/CEODashboard.tsx](../src/pages/CEODashboard.tsx)
- Function: `handleRefresh()`
- Why the warning appears:
  - The refresh button calls `/api/minerva-sync/all`.
  - The frontend treats the response as a warning whenever `success` is false.
  - `success` is false when either employee sync or attendance sync reports any errors.
- Underlying warning reasons in the sync service:
  - `Skipping transaction with incomplete data` when `emp_code` or `punch_time` is missing.
  - `Invalid punch_time format` when time parsing fails.
  - `Employee not found for emp_code=...; skipping attendance record` when a transaction cannot be mapped to a profile.
- Affected records:
  - The exact count is dynamic and depends on the live Minerva payload; the current environment returned 3889 transaction rows in the probe.
- Example records:
  - Records with missing `emp_code` or `punch_time`.
  - Malformed timestamp strings such as invalid ISO or naive timestamps that fail parsing.
  - Transactions for unknown `emp_code` values that do not map to a Supabase profile.

## 2) Two-month Minerva sync window

- File: [backend/app/services/minerva_sync.py](app/services/minerva_sync.py)
- Added: `_build_sync_window(reference_date=None)`
- Behavior:
  - Uses the previous month + current month automatically.
  - Example for 2026-06-09 -> `2026-05-01` to `2026-06-09`.
- The attendance sync path now calls the Minerva client with those date filters.

## 3) Date filtering support

- File: [backend/app/services/minerva_client.py](app/services/minerva_client.py)
- Verified API support:
  - The Minerva transaction endpoint accepts `start_date` and `end_date` query parameters.
  - The live probe returned HTTP 200 and the next-page URL contained `start_date=2026-05-01&end_date=2026-06-09`.
- Recommended implementation:
  - Use `start_date` and `end_date` on the transactions endpoint for all attendance refreshes.

## 4) Validation

- Test command:
  - `python -m pytest tests/test_minerva_sync.py -q`
- Result:
  - 18 passed, 2 warnings.

## 5) Modified files

- [backend/app/services/minerva_client.py](app/services/minerva_client.py)
- [backend/app/services/minerva_sync.py](app/services/minerva_sync.py)
- [backend/tests/test_minerva_sync.py](tests/test_minerva_sync.py)
