from datetime import datetime,timezone,timedelta
from decimal import Decimal
import json,socket
import pytest
from pydantic import ValidationError
from app.models import Mandate,ResearchRequest,ValuationInput,ConnectionInput
from app.storage import Store,digest
from app.settings import Settings
from app.valuation import valuation
from app.network import clean_url,public_addresses,is_primary,extract_document,select_excerpt,ResearchError
from app.research import evidence_check

def v(**kwargs):
    return ValuationInput(instrument='Synthetische Test-Aktie',currency='EUR',price='50',as_of=datetime.now(timezone.utc),period='Testjahr 2025',source_note='synthetische Testeingabe',**kwargs)

def test_public_mandate_has_no_personal_balances():
    m=Mandate();assert m.capital==0 and m.contribution==0 and m.interval_months==6
    assert not m.reserve_confirmed

def test_exact_valuation():
    r=valuation(v(eps='2',dividend_per_share='1.5'));assert r['pe']=='25.00' and r['gross_dividend_yield_pct']=='3.00'

def test_missing_dividend_is_not_zero():assert valuation(v())['gross_dividend_yield_pct'] is None

def test_zero_dividend_is_zero():assert valuation(v(dividend_per_share='0'))['gross_dividend_yield_pct']=='0.00'

@pytest.mark.parametrize('eps',['0','-1'])
def test_nonpositive_eps_not_multiple(eps):assert valuation(v(eps=eps))['pe'] is None

def test_stale_price_flag():
    x=v();x.as_of=datetime.now(timezone.utc)-timedelta(days=4);assert valuation(x)['stale']

def test_naive_time_refused():
    x=v();x.as_of=datetime(2025,1,1)
    with pytest.raises(ValueError):valuation(x)

def test_future_price_refused():
    x=v();x.as_of=datetime.now(timezone.utc)+timedelta(days=1)
    with pytest.raises(ValueError):valuation(x)

@pytest.mark.parametrize('value',['NaN','Infinity','-Infinity','0','-1'])
def test_invalid_prices(value):
    with pytest.raises(ValidationError):ValuationInput(instrument='x',currency='EUR',price=value,as_of=datetime.now(timezone.utc),period='2025',source_note='test')

def test_input_email_blocked():
    with pytest.raises(ValidationError):ResearchRequest(topic='mail user@example.org about investments')

def test_input_iban_blocked():
    with pytest.raises(ValidationError):ResearchRequest(topic='invest from DE89 3704 0044 0532 0130 00')

def test_unknown_fields_blocked():
    with pytest.raises(ValidationError):ResearchRequest(topic='Tencent KI',execute_trade=True)

@pytest.mark.parametrize('url',['http://example.com','https://user:pass@example.com','file:///etc/passwd','https://example.com:8443','https://example.com/\r\nX:1'])
def test_unsafe_url_rejected(url):
    with pytest.raises(ResearchError):clean_url(url)

def test_fragments_removed():assert clean_url('https://example.com/a#x')=='https://example.com/a'

def test_primary_domain_boundary():
    assert is_primary('https://www.tencent.com/foo')
    assert not is_primary('https://tencent.com.evil.example/foo')

@pytest.mark.parametrize('ip',['127.0.0.1','10.0.0.1','169.254.169.254','192.168.1.1','::1','fc00::1'])
def test_private_address_blocked(monkeypatch,ip):
    monkeypatch.setattr(socket,'getaddrinfo',lambda *a,**k:[(2,1,6,'',(ip,443))])
    with pytest.raises(ResearchError):public_addresses('attacker.example')

def test_dns_mixed_public_private_blocked(monkeypatch):
    monkeypatch.setattr(socket,'getaddrinfo',lambda *a,**k:[(2,1,6,'',('8.8.8.8',443)),(2,1,6,'',('127.0.0.1',443))])
    with pytest.raises(ResearchError):public_addresses('rebind.example')

def test_html_scripts_removed():
    text,_=extract_document('text/html',b'<html><script>steal()</script><p>Actual report text</p></html>')
    assert 'steal' not in text and 'Actual report text' in text

def test_excerpt_honestly_truncated():
    text='x'*50000+'cash flow grows'
    excerpt,truncated=select_excerpt(text);assert truncated and len(excerpt)<=16000

def test_journal_changes_detected(tmp_path):
    s=Store(tmp_path);s.event('decision',{'test':1});assert s.integrity()['ok']
    with s.db() as db:db.execute("UPDATE events SET payload=? WHERE seq=1",('{"forged":true}',))
    assert not s.integrity()['ok']

def test_watchlist_dedup_and_roundtrip(tmp_path):
    s=Store(tmp_path);n=len(s.watchlist());first=s.save_watch({'name':'Tencent'});assert len(s.watchlist())==n
    s.save_watch({'name':'New Test Co','theme':'Chancen'});assert len(Store(tmp_path).watchlist())==n+1

def test_secrets_not_public(tmp_path):
    cfg=Settings(tmp_path);cfg.save(ConnectionInput(brave_key='secret-search',anthropic_key='secret-model',model_id='test'))
    assert 'secret-' not in json.dumps(cfg.public())
    cfg.save(ConnectionInput(brave_key='',anthropic_key=None,model_id='test'))
    assert cfg.raw()['brave_key']=='secret-search'
    cfg.save(ConnectionInput(clear_secrets=True));assert cfg.raw()['brave_key']==''

@pytest.fixture
def evidence():
    return [{'id':'S001','text':'The annual free cash flow was 12 million EUR.','primary_domain':True},
            {'id':'S002','text':'Debt increased this year.','primary_domain':True}]

def candidate():
    return {'name':'Demo','source_ids':['S001','S002'],'facts':[{'text':'Cash flow was 12m','source_id':'S001','excerpt':'free cash flow was 12 million EUR.'}],'verdict':'Vertieft prüfen'}

def test_actual_excerpt_accepted(evidence):
    r=evidence_check(candidate(),evidence);assert len(r['facts'])==1 and not r['warnings']
    assert r['checks']['human_reviewed'] is False

def test_made_up_excerpt_removed(evidence):
    c=candidate();c['facts'][0]['excerpt']='free cash flow was 1200 million EUR.'
    r=evidence_check(c,evidence);assert not r['facts'] and r['verdict']=='Daten fehlen'

def test_forged_source_downgraded(evidence):
    c=candidate();c['source_ids'].append('FAKE');r=evidence_check(c,evidence)
    assert r['verdict']=='Daten fehlen' and 'FAKE' not in r['source_ids']
