import pytest
from app.research import run_research
from app.models import ResearchRequest
from app.network import ResearchError
from app.storage import now

class Search:
    calls=0
    def __call__(self,query,count=5):
        self.calls+=1
        return [{'title':'Demo Co official results','url':'https://www.tencent.com/demo-'+str(self.calls),
                 'snippet':'Demo Co annual report: synthetic test, not a real report.'}]

class FakeModel:
    def __init__(self,unsupported=False):self.calls=0;self.usage=[];self.unsupported=unsupported
    def __call__(self,purpose,data,schema,max_tokens=1000):
        self.calls+=1
        if self.calls==1:return {'candidates':[{'name':'Demo Co','theme':'KI & Wachstum','reason_to_research':'Synthetischer Testfall','discovery_source_ids':['D001']}]}
        if self.calls==2:return {'summary':'Synthetische Erstprüfung','candidates':[{
          'name':'Demo Co','theme':'KI & Wachstum','instrument':'','thesis':'Die Testthese braucht Originaldaten.',
          'why_now':'Synthetischer Testanlass','bear_case':'Im Test sind keine echten Daten vorhanden.',
          'dividend':'Nicht bekannt','valuation':'Kein aktueller Kurs vorhanden.',
          'china_risks':[],'open_questions':['Aktiengattung prüfen'],'source_ids':['S001','S002'],
          'facts':[{'text':'Die Quelle ist synthetisch.','source_id':'S001','excerpt':'This is synthetic source text for the test.'}],
          'verdict':'Vertieft prüfen'}]}
        return {'reviews':[{'name':'Demo Co','strongest_objection':'Keine echte Analyse mit diesen fiktiven Quellen möglich.',
                            'unsupported_facts':[0] if self.unsupported else [],'missing_checks':[], 'source_ids':['S001']}]}

def fetch(url,title='',sid=''):
    return {'id':sid,'title':title,'url':url,'text':'This is synthetic source text for the test. No real financial data.',
      'retrieved_at':now(),'method':'Synthetic','truncated':False,'primary_domain':True}

def req():return ResearchRequest(topic='Demo Co tests',themes=['KI & Wachstum'],max_candidates=1)

def test_full_pipeline_budget_and_citations():
    search=Search();model=FakeModel();stages=[]
    r=run_research(req(),search,model,lambda *x:stages.append(x),fetch=fetch)
    assert model.calls==3 and search.calls==3
    assert r['candidates'][0]['checks']['literal_excerpts_found']==1
    assert r['candidates'][0]['checks']['broker']=='Ungeprüft'
    assert any(x[0]=='challenge' for x in stages)

def test_counterreview_challenge_downgrades():
    r=run_research(req(),Search(),FakeModel(unsupported=True),lambda *x:None,fetch=fetch)
    assert r['candidates'][0]['verdict']=='Daten fehlen'

def test_no_originals_no_fake_report():
    def fail(*a,**kw):raise ResearchError('blocked')
    with pytest.raises(ResearchError,match='Keine Originalquelle'):run_research(req(),Search(),FakeModel(),lambda *x:None,fetch=fail)

def test_no_search_results_no_model():
    m=FakeModel()
    with pytest.raises(ResearchError,match='Keine Suchtreffer'):run_research(req(),lambda *a,**kw:[],m,lambda *a:None,fetch=fetch)
    assert m.calls==0

def test_cancellation_before_spend():
    s=Search();s.calls=0
    with pytest.raises(ResearchError,match='abgebrochen'):run_research(req(),s,FakeModel(),lambda *a:None,cancelled=lambda:True)
    assert s.calls==0

def test_name_not_in_search_results_rejected():
    m=FakeModel()
    def fake(*a,**kw):return {'candidates':[{'name':'Invented Co','theme':'Chancen','reason_to_research':'Hallucinated name','discovery_source_ids':['D001']}]}
    r=run_research(req(),Search(),fake,lambda *a:None,fetch=fetch)
    assert r['candidates']==[]
