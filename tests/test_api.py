import json
from fastapi.testclient import TestClient
import pytest
from app.main import create_app

@pytest.fixture
def client(tmp_path):
    app=create_app(tmp_path)
    with TestClient(app,base_url='http://127.0.0.1:8765') as c:
        c.headers['X-PIA-Token']=c.get('/api/bootstrap').json()['csrf']
        yield c

def test_home_and_health(client):
    assert client.get('/').status_code==200
    assert 'PIA' in client.get('/').text
    assert client.get('/api/health').json()['mode']=='local_research_only'

def test_csrf_enforced(client):
    r=client.post('/api/demo',headers={'X-PIA-Token':'invalid'},json={});assert r.status_code==403

def test_external_origin_enforced(client):
    assert client.get('/api/bootstrap',headers={'origin':'https://evil.example'}).status_code==403

def test_host_enforced(client):
    assert client.get('/api/bootstrap',headers={'host':'evil.example'}).status_code==403

def test_live_blocked_without_credentials(client):
    r=client.post('/api/research',json={'topic':'Tencent KI'});assert r.status_code==409
    assert not client.get('/api/runs').json()

def test_demo_separate_and_export(client):
    r=client.post('/api/demo',json={}).json();assert r['is_demo'] and r['result']['model_calls']==0
    md=client.get('/api/runs/'+r['id']+'/export?format=md')
    assert 'SYNTHETISCH' in md.text
    assert client.get('/api/integrity').json()['modified_runs']==[]

def test_watch_crud(client):
    old=len(client.get('/api/watchlist').json())
    w=client.post('/api/watchlist',json={'name':'Fiction Test','theme':'Chancen'}).json()
    assert len(client.get('/api/watchlist').json())==old+1
    w2={k:v for k,v in w.items() if k not in ('id','updated_at')};w2['broker_status']='In meiner App gefunden'
    assert client.put('/api/watchlist/'+w['id'],json=w2).status_code==200
    assert client.delete('/api/watchlist/'+w['id']).status_code==200
    assert len(client.get('/api/watchlist').json())==old

def test_secrets_excluded_from_exports(client):
    client.put('/api/connections',json={'provider':'anthropic','model_id':'test','brave_key':'search-secret123','anthropic_key':'model-secret123'})
    for path in ('/api/bootstrap','/api/export','/api/journal','/api/connections'):
        text=client.get(path).text
        assert 'search-secret123' not in text and 'model-secret123' not in text

def test_mandate_roundtrip(client):
    m=client.get('/api/bootstrap').json()['mandate'];m['contribution']='6000'
    assert client.put('/api/mandate',json=m).status_code==200
    assert client.get('/api/bootstrap').json()['mandate']['contribution']=='6000'

def test_decision_persisted_and_hashed(client):
    assert client.post('/api/decisions',json={'name':'Demo','decision':'Beobachten','note':'Testentscheidung, keine Order.'}).status_code==200
    j=client.get('/api/journal').json();assert j['integrity']['ok'] and j['events'][0]['payload']['kind']=='decision'

def test_trading_endpoint_absent(client):assert client.post('/api/order',json={}).status_code==404

def test_security_headers(client):
    r=client.get('/');assert 'frame-ancestors' in r.headers['content-security-policy'] and r.headers['cache-control']=='no-store'
