import os, httpx, uuid
from dotenv import load_dotenv
load_dotenv('.env')
url_admin = os.getenv('SUPABASE_URL') + '/auth/v1/admin/users'
headers_admin = {
    'apikey': os.getenv('SUPABASE_SERVICE_ROLE_KEY'),
    'Authorization': f"Bearer {os.getenv('SUPABASE_SERVICE_ROLE_KEY')}"
}
email = f"temp+{uuid.uuid4().hex[:8]}@example.com"
password = 'TempPass123!'
payload = {'email': email, 'password': password, 'email_confirm': True, 'app_metadata': {'provider': 'email', 'providers': ['email']}}
resp = httpx.post(url_admin, json=payload, headers=headers_admin, timeout=10)
print('create status', resp.status_code)
print(resp.text[:1000])
url_token = os.getenv('SUPABASE_URL') + '/auth/v1/token?grant_type=password'
headers_anon = {
    'apikey': os.getenv('SUPABASE_ANON_KEY'),
    'Authorization': f"Bearer {os.getenv('SUPABASE_ANON_KEY')}",
    'Content-Type': 'application/json'
}
resp2 = httpx.post(url_token, json={'email': email, 'password': password}, headers=headers_anon, timeout=10)
print('login status', resp2.status_code)
print(resp2.text[:1000])
