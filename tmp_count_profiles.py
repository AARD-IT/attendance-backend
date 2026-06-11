from app.db.supabase import SupabaseClient
profiles = SupabaseClient.get_all_profiles(role='EMPLOYEE')
real = [p for p in profiles if str(p.get('emp_code') or '').strip().isdigit()]
print('COUNT_REAL', len(real))
for p in real:
    print(p['email'], 'emp_code=', p.get('emp_code'), 'minerva_employee_id=', p.get('minerva_employee_id'))
