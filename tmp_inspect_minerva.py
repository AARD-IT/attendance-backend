import requests
from app.core.config import settings
base = settings.MINERVA_BASE_URL.rstrip('/')
url = base + settings.MINERVA_EMPLOYEE_ENDPOINT
headers = {
    'Authorization': 'Token ' + settings.MINERVA_API_TOKEN,
    'Accept': 'application/json',
}
resp = requests.get(url, headers=headers, timeout=180)
print('STATUS', resp.status_code)
print('TEXT', resp.text[:4000])
try:
    data = resp.json()
    print('TYPE', type(data).__name__)
    print('KEYS', list(data.keys())[:20] if isinstance(data, dict) else None)
    records = data.get('data') or data.get('results') or []
    print('RECORDS_LEN', len(records) if isinstance(records, list) else 'N/A')
    for i, item in enumerate(records[:40]):
        print('ITEM', i, item)
except Exception as e:
    print('JSON_ERR', repr(e))
