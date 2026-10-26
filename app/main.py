from __future__ import annotations
import hashlib,json,os,secrets,threading,uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit
from fastapi import FastAPI,HTTPException,Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse,Response,FileResponse
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
from .models import Mandate,ConnectionInput,ResearchRequest,WatchItem,DecisionInput,ValuationInput
from .storage import Store,now,digest,canonical
from .settings import Settings
from .providers import BraveSearch,Model
from .research import run_research
from .network import ResearchError
from .valuation import valuation

ROOT=Path(__file__).resolve().parents[1]
load_dotenv(ROOT/'.env')

def run_summary(r):
    return {k:r.get(k) for k in ('id','created_at','finished_at','status','topic','is_demo','stage','message','error','result_sha256')}

def markdown_report(run):
    result=run.get('result') or {}
    lines=['# PIA — Recherchebericht',f"\nStand: {run['created_at']}",f"\nFrage: {run['topic']}",
           '\n**SYNTHETISCHES BEDIENBEISPIEL — keine reale Anlageanalyse.**' if run.get('is_demo') else '\n**Research-Entwurf, kein Kaufauftrag. Alle Aussagen vor Anlageentscheidungen prüfen.**',
           '\n'+result.get('summary','')]
    for c in result.get('candidates',[]):
        lines.extend([f"\n## {c['name']} — {c['verdict']}"])
        for key,label in [('thesis','These'),('why_now','Warum jetzt untersuchen?'),('bear_case','Gegenthese'),('dividend','Dividende'),('valuation','Bewertung')]:
            lines.append(f"\n### {label}\n{c[key]}")
        lines.append('\n### Belegte Aussagen (Fundstelle mechanisch geprüft, Aussage nicht garantiert)')
        for f in c.get('facts',[]): lines.append(f"- {f['text']} [{f['source_id']}]\n  Fundstelle: {f['excerpt']}")
        if c.get('review'): lines.append('\n### Modell-Gegenprüfung\n'+c['review']['strongest_objection'])
        lines.append('\n### Offene Punkte\n'+'\n'.join('- '+x for x in c['open_questions']))
        if c.get('warnings'): lines.append('\n### Prüfhinweise\n'+'\n'.join('- '+x for x in c['warnings']))
    lines.append('\n## Quellen')
    for s in result.get('sources',[]):
        lines.append(f"\n{s['id']}: {s['title']}\n{s['url']}\nAbruf: {s['retrieved_at']}\nMethode: {s['method']}\nAuszugs-Hash: {s['excerpt_sha256']}")
    lines.append('\nErgebnis-SHA256: '+str(run.get('result_sha256',''))+'\nLokaler Hash, kein externer Zeitstempel.')
    return '\n'.join(lines)

def demo_result():
    text='Synthetisches Bedienbeispiel. Nordlicht Demo AG ist vollständig erfunden. Beispielumsatz 100 Mio. EUR; Beispiel-Cashflow 12 Mio. EUR. Diese Werte beschreiben kein existierendes Unternehmen.'
    source={'id':'S001','title':'Fiktives Geschäftsbericht-Beispiel','url':'https://example.invalid/nordlicht-demo','domain':'example.invalid',
       'text':text,'primary_domain':False,'retrieved_at':now(),'document_sha256':hashlib.sha256(text.encode()).hexdigest(),
       'excerpt_sha256':hashlib.sha256(text.encode()).hexdigest(),'method':'Synthetisch erzeugte Testdaten, kein Originalbericht.','truncated':False,'evidence':'Synthetisch'}
    return {'summary':'So sieht eine abgeschlossene Erstprüfung aus. Alle Unternehmen, Zahlen und Aussagen in diesem Bedienbeispiel sind erfunden.',
       'candidates':[{'name':'Nordlicht Demo AG · fiktiv','theme':'Dividendenqualität','instrument':'DEMO — nicht handelbar',
         'thesis':'Beispiel für eine These: Wiederkehrende Erlöse könnten eine Dividende tragen. Das ist ausschließlich eine Demonstration der Darstellung.',
         'why_now':'Hier würde eine belegte neue Entwicklung stehen, nicht nur eine interessante Unternehmensgeschichte.',
         'bear_case':'Ein hoher Investitionsbedarf könnte den ausschüttbaren Cashflow begrenzen. Der Gegencheck muss diese Annahme untersuchen.',
         'dividend':'Keine reale Dividende. Im Live-Bericht: Zeitraum, Ausschüttung, Deckung und Unsicherheiten getrennt.',
         'valuation':'Kein realer Kurs und keine Bewertung. Ohne passende Kursbasis wird keine Aussage „günstig“ ausgegeben.',
         'china_risks':[], 'open_questions':['Aktuellen Originalbericht lesen.','Aktiengattung, Kurs und Handelbarkeit separat prüfen.'],
         'source_ids':['S001'],'facts':[{'text':'Diese Gesellschaft und die angezeigten Werte sind erfunden.','source_id':'S001','excerpt':'Nordlicht Demo AG ist vollständig erfunden.'}],
         'verdict':'Daten fehlen','warnings':['Synthetisches Bedienbeispiel — nicht für Anlageentscheidungen verwenden.'],
         'checks':{'literal_excerpts_found':1,'semantic_review':'Nur demonstriert','human_reviewed':False,'broker':'Ungeprüft'},
         'review':{'name':'Nordlicht Demo AG · fiktiv','strongest_objection':'Beispiel einer getrennten Gegenprüfung: Eine Dividendenausschüttung ist nicht automatisch nachhaltig. Ohne belastbare Daten bleibt die Investmentthese offen.','unsupported_facts':[],'missing_checks':['Reale Daten fehlen vollständig.'],'source_ids':['S001']}}],
       'sources':[source],'discovery_hits':[],'fetch_failures':[],'usage':[],'search_calls':0,'model_calls':0,'method_version':'0.3.0'}

def create_app(data_dir=None):
    hosted = os.getenv('VERCEL') == '1' or os.getenv('PIA_HOSTED') == '1'
    if hosted:
        from .cloud import cloud_store, setup_app, cloud_authorized
        missing = [key for key in ('PIA_ACCESS_KEY', 'DATABASE_URL') if not os.getenv(key)]
        if len(os.getenv('PIA_ACCESS_KEY', '')) < 32 and 'PIA_ACCESS_KEY' not in missing:
            missing.append('PIA_ACCESS_KEY (mindestens 32 Zeichen)')
        if missing:
            return setup_app(missing)
        try:
            store = cloud_store(os.environ['DATABASE_URL'])
        except Exception:
            return setup_app(['Datenbankverbindung oder Datenbankschema prüfen'])
    data=Path(data_dir or os.getenv('PIA_DATA_DIR') or ('/tmp/pia' if hosted else ROOT/'data'))
    if not hosted: store=Store(data)
    settings=Settings(data, environment_only=hosted)
    token=hashlib.sha256(('pia-csrf:' + os.environ['PIA_ACCESS_KEY']).encode()).hexdigest() if hosted else secrets.token_urlsafe(32)
    executor=ThreadPoolExecutor(max_workers=1,thread_name_prefix='pia-research')
    gate=threading.Lock()
    for r in ([] if hosted else store.runs()):
        if r.get('status') in ('queued','running'):
            r.update(status='interrupted',message='Vorheriger Prozess wurde beendet. Kein automatischer Neustart.',finished_at=now());store.save_run(r)
    @asynccontextmanager
    async def lifespan(app):
        yield
        executor.shutdown(wait=False,cancel_futures=True)
    app=FastAPI(title='PIA Research',docs_url=None,redoc_url=None,openapi_url=None,lifespan=lifespan)
    app.state.store=store;app.state.settings=settings
    @app.middleware('http')
    async def local_only(request:Request,call_next):
        host=request.url.hostname
        if hosted and not cloud_authorized(request):
            return JSONResponse({'detail':'Anmeldung erforderlich.'},status_code=401,headers={'WWW-Authenticate':'Basic realm="PIA", charset="UTF-8"','Cache-Control':'no-store'})
        if not hosted and host not in ('127.0.0.1','localhost','::1'):
            return JSONResponse({'detail':'Nur lokale Nutzung erlaubt.'},status_code=403)
        origin=request.headers.get('origin')
        expected=f"{'https' if hosted else request.url.scheme}://{request.url.netloc}"
        if origin and origin!=expected:
            return JSONResponse({'detail':'Fremder Ursprung abgewiesen.'},status_code=403)
        try:
            if int(request.headers.get('content-length','0'))>100_000:
                return JSONResponse({'detail':'Anfrage zu groß.'},status_code=413)
        except ValueError: return JSONResponse({'detail':'Ungültige Anfrage.'},status_code=400)
        if request.method not in ('GET','HEAD','OPTIONS') and not secrets.compare_digest(request.headers.get('x-pia-token',''),token):
            return JSONResponse({'detail':'Lokale Sitzung abgelaufen. Seite neu laden.'},status_code=403)
        response=await call_next(request)
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['Referrer-Policy']='no-referrer'
        response.headers['Cache-Control']='no-store'
        response.headers['Content-Security-Policy']="default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        return response
    @app.exception_handler(RequestValidationError)
    async def validation_error(request,exc):
        fields=', '.join('.'.join(str(v) for v in e['loc'][1:]) for e in exc.errors())
        return JSONResponse({'detail':'Eingaben prüfen: '+fields},status_code=422)
    @app.get('/api/health')
    def health():return {'ok':True,'version':'0.4.0','mode':'hosted_private' if hosted else 'local_research_only'}
    @app.get('/api/bootstrap')
    def bootstrap():
        if hosted: store.expire_runs()
        return {'csrf':token,'hosted':hosted,'mandate':store.get('mandate'),'watchlist':store.watchlist(),
                'runs':[run_summary(x) for x in store.runs()],'connection':settings.public(),'integrity':store.integrity()}
    @app.put('/api/mandate')
    def put_mandate(payload:Mandate):
        value=payload.model_dump(mode='json');store.set('mandate',value);store.event('mandate_updated',{'sha256':digest(value)})
        return value
    @app.get('/api/connections')
    def connections():return settings.public()
    @app.put('/api/connections')
    def put_connections(payload:ConnectionInput):
        if hosted: raise HTTPException(403,'Zugangsdaten ausschließlich in den Vercel-Umgebungsvariablen ändern.')
        settings.save(payload);store.event('connections_updated',{'provider':payload.provider,'model_id':payload.model_id})
        return settings.public()
    @app.post('/api/connections/test')
    def test_connection():
        if not settings.public()['configured']: raise HTTPException(409,'Zuerst fehlende Zugangsdaten und Modell-ID ergänzen.')
        s=settings.raw();results={}
        try:
            BraveSearch(s['brave_key'])('Tencent investor relations',count=1)
            results['search']='Erfolgreich erreicht'
        except ResearchError as e: results['search']=str(e)
        try:
            raw=Model(s)('Antworte ausschließlich mit {"ok":true}. Verbindungsprüfung ohne Investmentinhalt.',{},
               {'type':'object','properties':{'ok':{'type':'boolean'}},'required':['ok'],'additionalProperties':False},max_tokens=128)
            results['model']='Erfolgreich erreicht' if raw.get('ok') is True else 'Antwortschema nicht bestätigt'
        except ResearchError as e: results['model']=str(e)
        results['ok']=all(results[k]=='Erfolgreich erreicht' for k in ('search','model'))
        results['at']=now();store.set('last_connection_test',results)
        return results
    @app.get('/api/watchlist')
    def watchlist():return store.watchlist()
    @app.post('/api/watchlist')
    def add_watch(payload:WatchItem):return store.save_watch(payload.model_dump())
    @app.put('/api/watchlist/{item_id}')
    def update_watch(item_id:str,payload:WatchItem):
        if not any(x['id']==item_id for x in store.watchlist()):raise HTTPException(404,'Eintrag nicht gefunden.')
        return store.save_watch(payload.model_dump(),item_id)
    @app.delete('/api/watchlist/{item_id}')
    def delete_watch(item_id:str):store.delete_watch(item_id);return {'ok':True}
    @app.post('/api/decisions')
    def decision(payload:DecisionInput):
        if payload.run_id and not store.run(payload.run_id): raise HTTPException(404,'Recherche nicht gefunden.')
        return {'hash':store.event('decision',payload.model_dump()),'ok':True}
    @app.get('/api/journal')
    def journal():return {'events':list(reversed(store.events())),'integrity':store.integrity()}
    @app.post('/api/valuation')
    def calculate(payload:ValuationInput):
        try: result=valuation(payload)
        except ValueError as e:raise HTTPException(422,str(e))
        store.event('manual_valuation',result)
        return result
    def worker(rid,request):
        r=store.run(rid);r.update(status='running');store.save_run(r)
        def progress(stage,message):
            r=store.run(rid);r.update(stage=stage,message=message);store.save_run(r)
        try:
            s=settings.raw()
            from .budget import time_budget
            with time_budget(240 if hosted else None):
                result=run_research(request,BraveSearch(s['brave_key']),Model(s),progress,
                                    cancelled=lambda:bool(store.run(rid).get('cancel_requested')))
            r=store.run(rid)
            if r.get('cancel_requested'): raise ResearchError('Recherche auf Wunsch abgebrochen.')
            r.update(status='completed',result=result,result_sha256=digest(result),finished_at=now())
            store.save_run(r);store.event('research_completed',{'run_id':rid,'result_sha256':r['result_sha256']})
        except Exception as e:
            r=store.run(rid);r.update(status='cancelled' if r.get('cancel_requested') else 'failed',finished_at=now(),
               error=str(e) if isinstance(e,ResearchError) else 'Recherche fehlgeschlagen. Kein Ergebnis als vollständig ausgegeben.',
               message='Kein vollständiger Bericht. Bereits erfolgte API-Aufrufe können Kosten verursachen.')
            store.save_run(r);store.event('research_stopped',{'run_id':rid,'status':r['status']})
    @app.post('/api/research')
    def research(payload:ResearchRequest):
        if not settings.public()['configured']: raise HTTPException(409,'Live-Recherche noch nicht verbunden. Unter Verbindungen Modell und Brave-Suche einrichten.')
        with gate:
            if not hosted and any(r['status'] in ('queued','running') for r in store.runs()): raise HTTPException(409,'Eine Recherche läuft bereits.')
            rid=uuid.uuid4().hex[:16]
            run={'id':rid,'created_at':now(),'status':'queued','stage':'start','message':'Recherche wird gestartet.',
                 'topic':payload.topic,'request':payload.model_dump(),'is_demo':False,'cancel_requested':False,
                 'mandate_sha256':digest(store.get('mandate')),
                 'provider':settings.raw()['provider'],'model_id':settings.raw()['model_id'],'region':settings.raw()['region']}
            if hosted:
                if not store.claim_run(run): raise HTTPException(409,'Eine Recherche läuft bereits. Verwaiste Läufe werden nach sechs Minuten freigegeben.')
            else:
                store.save_run(run)
            store.event('research_started',{'run_id':rid,'request':payload.model_dump()})
            if not hosted: executor.submit(worker,rid,payload)
        return run_summary(run) | {'execution_mode':'request' if hosted else 'local_worker'}
    @app.post('/api/runs/{rid}/execute')
    def execute(rid:str):
        if not hosted: raise HTTPException(404,'Nur im Onlinebetrieb verfügbar.')
        run=store.begin_run(rid)
        if not run: raise HTTPException(409,'Recherche fehlt, läuft bereits oder ist abgeschlossen.')
        worker(rid,ResearchRequest.model_validate(run['request']))
        return run_summary(store.run(rid))
    @app.post('/api/demo')
    def demo():
        rid=uuid.uuid4().hex[:16];result=demo_result()
        run={'id':rid,'created_at':now(),'finished_at':now(),'status':'completed','stage':'done','message':'Synthetisches Beispiel.',
             'topic':'Bedienbeispiel — keine reale Anlageanalyse','is_demo':True,'result':result,'result_sha256':digest(result)}
        store.save_run(run);store.event('demo_created',{'run_id':rid,'result_sha256':run['result_sha256']})
        return run
    @app.get('/api/runs')
    def runs():return [run_summary(x) for x in store.runs()]
    @app.get('/api/runs/{rid}')
    def get_run(rid:str):
        if hosted: store.expire_runs()
        r=store.run(rid)
        if not r:raise HTTPException(404,'Recherche nicht gefunden.')
        return r
    @app.post('/api/runs/{rid}/cancel')
    def cancel(rid:str):
        r=store.run(rid)
        if not r:raise HTTPException(404,'Recherche nicht gefunden.')
        if r['status'] in ('queued','running'):
            r['cancel_requested']=True;r['message']='Abbruch nach dem laufenden API-/Quellenaufruf.';store.save_run(r)
        return run_summary(r)
    @app.get('/api/runs/{rid}/export')
    def export_run(rid:str,format:str='json'):
        r=store.run(rid)
        if not r:raise HTTPException(404,'Recherche nicht gefunden.')
        if format=='md':return Response(markdown_report(r),media_type='text/markdown',headers={'Content-Disposition':f'attachment; filename="PIA_{rid}.md"'})
        return Response(json.dumps(r,ensure_ascii=False,indent=2),media_type='application/json',headers={'Content-Disposition':f'attachment; filename="PIA_{rid}.json"'})
    @app.get('/api/integrity')
    def integrity():
        problems=[]
        for r in store.runs():
            if r.get('result') and digest(r['result'])!=r.get('result_sha256'): problems.append(r['id'])
        return store.integrity() | {'modified_runs':problems}
    @app.get('/api/export')
    def export():
        payload={'version':'0.4.0','exported_at':now(),'mandate':store.get('mandate'),'watchlist':store.watchlist(),
                 'runs':store.runs(),'journal':store.events(),'integrity':store.integrity()}
        payload['export_sha256']=digest(payload)
        return Response(json.dumps(payload,ensure_ascii=False,indent=2),media_type='application/json',headers={'Content-Disposition':'attachment; filename="PIA_Research_Backup.json"'})
    app.mount('/assets',StaticFiles(directory=ROOT/'static'),name='assets')
    @app.get('/')
    def index():return FileResponse(ROOT/'static'/'index.html')
    return app

app=create_app()
