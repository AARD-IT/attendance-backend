import sys
import os
sys.path.append(os.path.abspath('.'))

from app.services.dashboard_analytics_service import analytics_service

emp_id = "917b17d8-0237-42f7-99a1-69cb28cbd8a6"
try:
    profiles = analytics_service._fetch_records("profiles")
    profile = next((p for p in profiles if str(p.get("id")) == emp_id), None)
    print("PROFILE FOR ID:", profile)

    records = analytics_service._fetch_records("attendance_records")
    emp_records = [r for r in records if str(r.get("employee_id")) == emp_id]
    print(f"Total attendance records for this employee: {len(emp_records)}")
    if emp_records:
        dates = sorted(list(set([r.get("attendance_date") for r in emp_records])))
        print("Dates with records:", dates)
except Exception as e:
    print("Error:", e)
