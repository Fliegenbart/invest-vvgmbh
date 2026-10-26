import json
import httpx
import pytest
import boto3
from app.providers import BraveSearch,Model
from app.network import ResearchError

SETTINGS={'provider':'anthropic','model_id':'test-only-model','region':'eu-central-1','aws_profile':'','anthropic_key':'test-secret','brave_key':'test-search'}

def mock_http(monkeypatch,handler):
    original=httpx.Client
    monkeypatch.setattr(httpx,'Client',lambda **kw:original(transport=httpx.MockTransport(handler)))

def test_brave_request_contract(monkeypatch):
    def handle(request):
        assert request.url.host=='api.search.brave.com'
        assert request.headers['X-Subscription-Token']=='test-search'
        assert request.url.params['q']=='public company results'
        return httpx.Response(200,json={'web':{'results':[{'title':'A','url':'https://example.com','description':'result'}]}})
    mock_http(monkeypatch,handle)
    assert BraveSearch('test-search')('public company results')[0]['snippet']=='result'

def test_anthropic_contract_and_usage(monkeypatch):
    def handle(request):
        body=json.loads(request.content)
        assert request.url.host=='api.anthropic.com' and request.headers['x-api-key']=='test-secret'
        assert body['model']=='test-only-model' and body['max_tokens']==128
        assert 'Werkzeuge' in body['system']
        return httpx.Response(200,json={'stop_reason':'end_turn','content':[{'type':'text','text':'{"ok":true}'}],'usage':{'input_tokens':1,'output_tokens':1}})
    mock_http(monkeypatch,handle)
    m=Model(SETTINGS);assert m('test',{}, {},max_tokens=128)=={'ok':True} and m.calls==1 and len(m.usage)==1

def test_bedrock_contract(monkeypatch):
    class Client:
        def converse(self,**kwargs):
            assert kwargs['modelId']=='test-only-model' and kwargs['messages'][0]['role']=='user'
            return {'stopReason':'end_turn','output':{'message':{'content':[{'text':'{"ok":true}'}]}},'usage':{'inputTokens':1,'outputTokens':1}}
    class Session:
        def __init__(self,**kwargs):assert kwargs['region_name']=='eu-central-1'
        def client(self,name,**kwargs):assert name=='bedrock-runtime';return Client()
    monkeypatch.setattr(boto3,'Session',Session)
    m=Model({**SETTINGS,'provider':'bedrock'});assert m('test',{}, {})['ok'] is True

@pytest.mark.parametrize('output',['{"ok":true,"ok":false}','{"value":NaN}','invalid text'])
def test_malformed_model_output_rejected(monkeypatch,output):
    mock_http(monkeypatch,lambda request:httpx.Response(200,json={'stop_reason':'end_turn','content':[{'type':'text','text':output}]}))
    with pytest.raises(ResearchError,match='JSON'):Model(SETTINGS)('test',{}, {})

def test_truncated_output_rejected(monkeypatch):
    mock_http(monkeypatch,lambda request:httpx.Response(200,json={'stop_reason':'max_tokens','content':[{'type':'text','text':'{"ok":true}'}]}))
    with pytest.raises(ResearchError,match='unvollständig'):Model(SETTINGS)('test',{}, {})

def test_provider_error_no_response_leak(monkeypatch):
    mock_http(monkeypatch,lambda request:httpx.Response(401,text='sensitive-service-message'))
    with pytest.raises(ResearchError) as e:Model(SETTINGS)('test',{}, {})
    assert 'sensitive' not in str(e.value)

def test_budget_blocks_fourth_model_call():
    m=Model(SETTINGS);m.calls=3
    with pytest.raises(ResearchError,match='Modelllimit'):m('test',{}, {})
