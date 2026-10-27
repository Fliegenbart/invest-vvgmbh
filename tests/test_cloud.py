import base64
import time
import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app.storage import Store
from app.settings import Settings
from app.budget import time_budget, timeout
from app.network import ResearchError

KEY='test-only-' + 'q'*40

class FakeHostedStore(Store):
    """In-memory/local test double, NOT a PostgreSQL integration test."""
    def expire_runs(self): pass
    def claim_run(self, run):
        if any(x['status'] in ('queued','running') for x in self.runs()): return False
        self.save_run(run); return True
    def begin_run(self, rid):
        run=self.run(rid)
        if not run or run['status']!='queued': return None
        run['status']='running'; self.save_run(run); return run

@pytest.fixture
def hosted(tmp_path, monkeypatch):
    monkeypatch.setenv('PIA_HOSTED','1')
    monkeypatch.setenv('PIA_ACCESS_KEY',KEY)
    monkeypatch.setenv('DATABASE_URL','postgresql://test.invalid/not-a-real-credential')
    for key in ('PIA_PROVIDER','PIA_MODEL_ID','BRAVE_API_KEY','ANTHROPIC_API_KEY'):
        monkeypatch.delenv(key,raising=False)
    store=FakeHostedStore(tmp_path)
    monkeypatch.setattr('app.cloud.cloud_store',lambda _:store)
    app=create_app(tmp_path)
    with TestClient(app,base_url='https://pia.example') as client:
        client.auth=('pia',KEY)
        client.headers['X-PIA-Token']=client.get('/api/bootstrap').json()['csrf']
        yield client,store

@pytest.mark.parametrize('path',['/','/api/bootstrap','/api/export','/assets/app.js'])
def test_every_private_surface_requires_login(hosted,path):
    client,_=hosted
    response=client.get(path,auth=('pia','incorrect'))
    assert response.status_code==401
    assert 'Basic' in response.headers['www-authenticate']

@pytest.mark.parametrize('header',['Basic !!!','Basic ', 'Bearer invalid', ''])
def test_malformed_auth_is_rejected(hosted,header):
    client,_=hosted
    assert client.get('/api/bootstrap',auth=None,headers={'Authorization':header}).status_code==401

def test_hosted_mode_and_env_settings(hosted):
    client,_=hosted
    data=client.get('/api/bootstrap').json()
    assert data['hosted'] is True and data['connection']['managed_by_environment'] is True
    assert client.get('/api/health').json()['mode']=='hosted_private'
    assert client.put('/api/connections',json={}).status_code==403
    assert KEY not in client.get('/api/export').text

def test_no_default_personal_capital(hosted):
    client,_=hosted
    m=client.get('/api/bootstrap').json()['mandate']
    assert m['capital']=='0' and m['contribution']=='0'

def test_hosted_origin_and_csrf(hosted):
    client,_=hosted
    assert client.post('/api/demo',json={},headers={'origin':'https://evil.example'}).status_code==403
    assert client.post('/api/demo',json={},headers={'X-PIA-Token':'wrong'}).status_code==403
    assert client.post('/api/demo',json={},headers={'origin':'https://pia.example'}).status_code==200

def test_csrf_stable_across_instances(hosted,tmp_path):
    client,_=hosted
    first=client.get('/api/bootstrap').json()['csrf']
    with TestClient(create_app(tmp_path),base_url='https://pia.example') as another:
        another.auth=('pia',KEY)
        assert another.get('/api/bootstrap').json()['csrf']==first

def test_request_executes_once(hosted,monkeypatch):
    client,store=hosted
    monkeypatch.setenv('PIA_PROVIDER','anthropic')
    monkeypatch.setenv('PIA_MODEL_ID','fake-model')
    monkeypatch.setenv('BRAVE_API_KEY','fake-search')
    monkeypatch.setenv('ANTHROPIC_API_KEY','fake-key')
    calls=[]
    monkeypatch.setattr('app.main.run_research',lambda *a,**kw: calls.append(1) or {'candidates':[],'summary':'Test'})
    response=client.post('/api/research',json={'topic':'Public research question'}).json()
    assert response['execution_mode']=='request' and calls==[]
    rid=response['id']
    assert client.post('/api/runs/'+rid+'/execute',json={}).json()['status']=='completed'
    assert calls==[1]
    assert client.post('/api/runs/'+rid+'/execute',json={}).status_code==409

def test_unconfigured_cloud_fails_closed(monkeypatch,tmp_path):
    monkeypatch.setenv('VERCEL','1')
    monkeypatch.delenv('PIA_ACCESS_KEY',raising=False)
    monkeypatch.delenv('DATABASE_URL',raising=False)
    with TestClient(create_app(tmp_path)) as client:
        assert client.get('/').status_code==503
        assert client.get('/api/bootstrap').status_code==503
        assert client.get('/api/health').json()['mode']=='setup_required'
    assert not (tmp_path/'pia.sqlite3').exists()

def test_budget_stops(monkeypatch):
    with time_budget(2):
        assert 0 < timeout(100) <= 2
        monkeypatch.setattr('app.budget.time.monotonic',lambda:1e15)
        with pytest.raises(ResearchError): timeout(1)


def browser_login(client, password=KEY, origin='https://pia.example'):
    client.auth=None
    return client.post('/login',data={'username':'pia','password':password},
                       headers={'Origin':origin},follow_redirects=False)


def test_browser_gets_login_form_instead_of_basic_dialog(hosted):
    client,_=hosted
    client.auth=None
    response=client.get('/',headers={'Accept':'text/html'},follow_redirects=False)
    assert response.status_code==303
    assert response.headers['location']=='/login'
    assert 'www-authenticate' not in response.headers
    login=client.get('/login')
    assert login.status_code==200
    assert 'name="username"' in login.text and 'name="password"' in login.text
    assert 'type="password"' in login.text and 'method="post"' in login.text
    assert 'Tencent' not in login.text and KEY not in login.text
    assert client.get('/login.css').status_code==200
    assert client.get('/assets/app.js').status_code==401


def test_browser_can_recover_from_cached_incorrect_basic_credentials(hosted):
    client,_=hosted
    response=client.get('/',auth=('pia','old-password'),headers={'Accept':'text/html'},follow_redirects=False)
    assert response.status_code==303 and response.headers['location']=='/login'
    assert client.get('/login',auth=('pia','old-password')).status_code==200


def test_form_login_creates_private_session_and_serves_app(hosted):
    client,_=hosted
    response=browser_login(client)
    assert response.status_code==303 and response.headers['location']=='/'
    cookie=response.headers['set-cookie']
    assert '__Host-pia_session=' in cookie
    assert 'HttpOnly' in cookie and 'Secure' in cookie and 'SameSite=strict' in cookie
    assert 'Domain=' not in cookie and 'Path=/' in cookie
    assert KEY not in cookie
    assert client.get('/').status_code==200
    assert client.get('/assets/app.js').status_code==200
    assert client.get('/api/bootstrap').json()['hosted'] is True


def test_browser_session_is_valid_on_another_app_instance(hosted,tmp_path):
    client,_=hosted
    assert browser_login(client).status_code==303
    with TestClient(create_app(tmp_path),base_url='https://pia.example') as another:
        another.cookies.update(client.cookies)
        assert another.get('/api/bootstrap').status_code==200


def test_form_login_rejects_wrong_password_without_native_auth_dialog(hosted):
    client,_=hosted
    response=browser_login(client,password='incorrect-password')
    assert response.status_code==401
    assert 'www-authenticate' not in response.headers and 'set-cookie' not in response.headers
    assert 'role="alert"' in response.text
    assert 'incorrect-password' not in response.text
    assert client.get('/api/bootstrap').status_code==401


@pytest.mark.parametrize('origin',['https://evil.example','null',''])
def test_form_login_rejects_cross_origin_and_missing_origin(hosted,origin):
    client,_=hosted
    response=browser_login(client,origin=origin)
    assert response.status_code==403
    assert 'set-cookie' not in response.headers


def test_form_login_rejects_oversized_body(hosted):
    client,_=hosted
    client.auth=None
    response=client.post('/login',content='password='+'x'*5000,
                        headers={'Origin':'https://pia.example','Content-Type':'application/x-www-form-urlencoded'})
    assert response.status_code==413


def test_form_login_rejects_non_form_body(hosted):
    client,_=hosted
    client.auth=None
    response=client.post('/login',json={'username':'pia','password':KEY},headers={'Origin':'https://pia.example'})
    assert response.status_code==415


def test_session_tampering_expiration_and_key_rotation_are_rejected(hosted,monkeypatch):
    client,_=hosted
    response=browser_login(client)
    assert response.status_code==303
    cookie=client.cookies.get('__Host-pia_session')
    assert cookie
    client.cookies.clear()
    client.cookies.set('__Host-pia_session',cookie+'tampered')
    assert client.get('/api/bootstrap').status_code==401
    client.cookies.clear()
    browser_login(client)
    current_time=time.time()
    with monkeypatch.context() as clock:
        clock.setattr('app.auth.time.time',lambda:current_time+13*60*60)
        assert client.get('/api/bootstrap').status_code==401
    monkeypatch.setenv('PIA_ACCESS_KEY','rotated-'+'z'*40)
    assert client.get('/api/bootstrap').status_code==401


def test_logout_needs_csrf_and_clears_browser_session(hosted):
    client,_=hosted
    assert browser_login(client).status_code==303
    assert client.post('/api/logout',json={},headers={'X-PIA-Token':'incorrect'}).status_code==403
    csrf=client.get('/api/bootstrap').json()['csrf']
    response=client.post('/api/logout',json={},headers={'X-PIA-Token':csrf})
    assert response.status_code==200 and response.json()['ok'] is True
    assert 'Max-Age=0' in response.headers['set-cookie']
    assert client.get('/api/bootstrap').status_code==401


def test_unauthenticated_api_never_opens_native_basic_dialog(hosted):
    client,_=hosted
    client.auth=None
    response=client.get('/api/bootstrap')
    assert response.status_code==401
    assert 'www-authenticate' not in response.headers
