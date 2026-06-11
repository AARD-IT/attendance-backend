import httpx
from app.core.config import settings

url = f"{settings.SUPABASE_URL.rstrip('/')}/rest/v1/employee_shift_assignments"
headers = {
    'apikey': settings.SUPABASE_SERVICE_ROLE_KEY,
    'Authorization': f"Bearer {settings.SUPABASE_SERVICE_ROLE_KEY}",
    'Content-Type': 'application/json',
}

print('URL=', url)
r = httpx.get(url, headers=headers, timeout=20.0)
print('STATUS=', r.status_code)
print('TEXT=', r.text[:1000])
print('HEADERS=', dict(r.headers))
