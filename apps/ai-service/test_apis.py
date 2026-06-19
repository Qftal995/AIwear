
"""Comprehensive API test — tests Python service directly (port 5001)"""
import urllib.request, urllib.parse, json, ssl, sys
ctx = ssl.create_default_context()

BASE = 'http://127.0.0.1:5001'
PASS = 0; FAIL = 0

def check(name, ok, detail=''):
    global PASS, FAIL
    if ok: PASS += 1; print(f'  [PASS] {name}')
    else: FAIL += 1; print(f'  [FAIL] {name} - {detail}')

def api(method, path, data=None):
    url = BASE + path
    body = None
    if data is not None:
        body = json.dumps(data, ensure_ascii=False).encode('utf-8')
    req = urllib.request.Request(url, data=body, method=method)
    if body:
        req.add_header('Content-Type', 'application/json')
    try:
        with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
            raw = resp.read().decode('utf-8')
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        try:
            raw = e.read().decode('utf-8')
            return e.code, json.loads(raw) if raw else {}
        except:
            return e.code, {}

# ── Health ──
print('\n=== Health ===')
code, body = api('GET', '/api/health')
check('health endpoint', code == 200 and body.get('status') == 'ok', f'{code} {body}')

# ── Session Stats ──
print('\n=== Session Stats ===')
code, body = api('GET', '/api/session-stats')
check('global stats', code == 200, f'{code}')
check('has total_tokens', 'total_tokens' in body.get('data', {}), str(body.get('data', {}).keys())[:200])

# ── Traces ──
print('\n=== Traces ===')
code, body = api('GET', '/api/traces')
check('traces list', code == 200 and 'data' in body, f'{code}')
check('has sessions count', 'sessions' in body.get('data', {}), str(body.get('data'))[:200])

# ── Wardrobe ──
print('\n=== Wardrobe ===')
code, body = api('GET', '/api/wardrobe/default')
check('wardrobe list for default', code == 200, f'{code}')
check('returns data array', isinstance(body.get('data'), list), f'type={type(body.get("data"))}')

# DELETE
code, body = api('DELETE', '/api/wardrobe/fake_test_id_12345')
check('DELETE nonexistent returns ok', code in (200, 404), f'{code} {body.get("message","")}')

code, body = api('DELETE', '/api/wardrobe')
check('DELETE without url requires url', code == 400, f'{code}')

code, body = api('DELETE', '/api/wardrobe?url=not_a_real_url_test')
check('DELETE by nonexistent url returns 404', code == 404, f'{code}')

# ── Search Image ──
print('\n=== Search ===')
code, body = api('POST', '/api/search-image', {'query': 'test'})
check('search-image POST works', code in (200, 400), f'{code}')  # 400 if no file

# ── Validate Image ──
print('\n=== Validate ===')
try:
    req = urllib.request.Request(BASE + '/api/validate-image', method='POST')
    with urllib.request.urlopen(req, timeout=5, context=ctx) as resp:
        code = resp.status
    check('validate-image endpoint exists', code in (200, 400, 415), f'{code}')
except urllib.error.HTTPError as e:
    check('validate-image endpoint exists', True, 'expected error without file')

print(f'\n{"="*40}')
print(f'Results: {PASS} passed, {FAIL} failed')
print(f'{"="*40}')
sys.exit(0 if FAIL == 0 else 1)

