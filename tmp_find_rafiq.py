from app.db.supabase import SupabaseClient
profiles = SupabaseClient.get_all_profiles(role='EMPLOYEE')
for p in profiles:
    if 'rafiq' in str(p.get('email','')) or 'madhu' in str(p.get('email','')) or str(p.get('emp_code') or '') in ('15','16'):
        print('FOUND', p)
