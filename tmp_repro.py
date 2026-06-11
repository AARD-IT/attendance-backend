from unittest.mock import patch
from app.services.dashboard_analytics_service import DashboardAnalyticsService
profile=[{"id":"emp-1","full_name":"Rafiq","department":"Ops"}]
assignments=[{"id":"shift-1","employee_id":"emp-1","minerva_employee_id":"M-1","employee_name":"Rafiq","employee_email":"rafiq@company.com","cc_email":"manager@company.com","shift_type":"Shift 2","effective_from":"2026-06-01","effective_to":"2026-06-30","is_active":True}]
record={"id":"rec-1","employee_id":"emp-1","attendance_date":"2026-06-10","first_punch":"2026-06-10T14:40:00+00:00","last_punch":"2026-06-10T21:50:00+00:00","total_hours":7.0}
with patch.object(DashboardAnalyticsService, '_fetch_records', side_effect=lambda table: profile if table=='profiles' else assignments if table=='employee_shift_assignments' else [record]):
    print('classification', DashboardAnalyticsService._classify_record(record))
    print('thresholds', DashboardAnalyticsService._shift_thresholds(record))
