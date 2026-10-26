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
