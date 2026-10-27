from __future__ import annotations
import re
from datetime import datetime,timezone
from pydantic import ValidationError
from .models import ResearchRequest,Discovery,Analysis,Review
from .network import ResearchError,ModelSchemaError,clean_url,fetch_source,is_primary,normalize_text
from .storage import now,digest

THEME_QUERIES={
 'Dividendenqualität':'dividend growth free cash flow annual results investor relations',
 'KI & Wachstum':'AI cloud profitable free cash flow earnings investor relations',
 'Chancen':'space technology profitable growth capital expenditure investor relations',
}

DISCOVER='''Entdecke maximal die gewünschte Anzahl konkreter Unternehmen, die zur öffentlichen Recherchefrage passen. Die Suchtreffer sind nur Hinweise. Nenne nur Namen, die in den Treffern tatsächlich vorkommen. Verwende discovery_source_ids als Liste mit mindestens einer vorhandenen Suchtreffer-ID pro Kandidat. reason_to_research ist ein kurzer Satz mit höchstens 250 Zeichen. theme muss exakt einer der vorgegebenen Kategorien entsprechen. Suche nicht zwanghaft drei Namen; es dürfen null sein. Keine bloßen Branchenfonds als Ersatz, wenn die Frage Einzelaktien verlangt. Gattungen, Listing und Finanzzahlen noch NICHT behaupten. Auswahl ist eine Recherchepriorität, keine Kaufempfehlung.'''
ANALYZE='''Erstelle eine belegte Research-Erstprüfung ausschließlich aus den bereitgestellten Originaltextauszügen. Höchstens drei Kandidaten. Alle Fakten nur in facts und dort mit einer vorhandenen source_id und einem wörtlichen kurzen zusammenhängenden excerpt aus dem jeweiligen Quellenpaket belegen. Pro Fakt eine Quelle, pro Kandidat maximal fünf Fakten. Wörtliche Auszüge sind Fundstellen, keine automatische semantische Verifikation. Alle anderen Abschnitte als Interpretation der belegten Fakten formulieren und die source_ids angeben. Keine neue unbelegte Finanzkennzahl in Prosa. Veraltete Ergebnisse und teilweise gelesene Dokumente ausdrücklich markieren. Unbekannte Kennzahlen nicht mit null verwechseln. Ohne aktuelle Kursbasis und überprüfte Aktiengattung keine Bewertung als günstig und keine Kursziele. Halte einen Dividendenausblick von einer zugesagten Zahlung getrennt. China-Risiken differenziert prüfen. Nicht belegt/keine Aussage ist zulässig. open_questions muss die entscheidenden Lücken enthalten. Die Bewertung ist immer eine Research-Einschätzung, nie Kauf/Verkauf.'''
REVIEW='''Prüfe die fertige Erstprüfung kritisch anhand derselben Originalauszüge. Du bist ein zweiter Modelldurchlauf, keine unabhängige Datenquelle. Stelle die stärkste Gegenthese auf. Nenne in unsupported_facts die nullbasierten Indizes der Fakten, deren Aussage nicht durch ihren zugeordneten Auszug getragen wird (falsche Perioden, Währungen, Verwechslungen, bereinigter/unbereinigter Cashflow, Rechtsstruktur). Nenne weitere offene Checks. Gib zu Gegenargumenten vorhandene source_ids an; erfinde keine Fakten. Genau ein Review je Kandidat; identische Namen verwenden.'''

def queries_for(request:ResearchRequest):
    year=datetime.now(timezone.utc).year
    return [f'{request.topic} {THEME_QUERIES[t]} {year}' for t in request.themes][:3]

def evidence_check(candidate,sources):
    """Mechanical citation/substring checks, NOT semantic truth certification."""
    lookup={s['id']:s for s in sources}; problems=[]; accepted=[]
    ids=candidate['source_ids']
    if any(x not in lookup for x in ids): problems.append('Unbekannte Quellen-ID im Entwurf.')
    candidate['source_ids']=[x for x in dict.fromkeys(ids) if x in lookup]
    for fact in candidate['facts']:
        src=lookup.get(fact['source_id'])
        if not src or normalize_text(fact['excerpt']).casefold() not in normalize_text(src['text']).casefold():
            problems.append('Fakt ohne auffindbare wörtliche Fundstelle entfernt.'); continue
        accepted.append(fact)
        if fact['source_id'] not in candidate['source_ids']: candidate['source_ids'].append(fact['source_id'])
    candidate['facts']=accepted
    if not accepted: problems.append('Keine belegte Einzelaussage vorhanden.')
    if not any(lookup[x]['primary_domain'] for x in candidate['source_ids']):
        problems.append('Keine Quelle aus der gepflegten Primärdomain-Liste; Herkunft manuell prüfen.')
    if len(candidate['source_ids'])<2: problems.append('Weniger als zwei gelesene Originalauszüge; Datenbasis begrenzt.')
    candidate['checks']={'citation_ids_known':all(x in lookup for x in ids),'literal_excerpts_found':len(accepted),
                         'semantic_review':'Noch nicht erfolgt','human_reviewed':False,
                         'broker':'Ungeprüft','live_quote':'Nicht automatisch angebunden'}
    candidate['warnings']=list(dict.fromkeys(problems))
    if problems and candidate['verdict']!='Verwerfen': candidate['verdict']='Daten fehlen'
    return candidate

def run_research(request:ResearchRequest,search,model,progress,fetch=fetch_source,cancelled=lambda:False):
    hits=[]; originals=[]; failures=[]; discovery=None; result=None
    def tick(stage,message):
        from .budget import timeout
        timeout(1)
        if cancelled(): raise ResearchError('Recherche auf Wunsch abgebrochen.')
        progress(stage,message)
    def add_hits(query):
        tick('search','Öffentliche Suchbegriffe recherchieren')
        rows=search(query,count=5)
        for r in rows:
            try: url=clean_url(r['url'])
            except (ResearchError,KeyError): continue
            if any(x['url']==url for x in hits): continue
            hits.append(dict(r,url=url,id=f'D{len(hits)+1:03}',query=query))
    for query in queries_for(request): add_hits(query)
    if not hits: raise ResearchError('Keine Suchtreffer erhalten. Keine Namen oder Empfehlungen erfunden.')
    tick('discover','Recherchekandidaten aus Suchhinweisen auswählen')
    try:
        discovery=Discovery.model_validate(model(DISCOVER,{'question':request.topic,'max_candidates':request.max_candidates,
             'themes':request.themes,'search_hits':hits},Discovery.model_json_schema(),max_tokens=1600))
    except ValidationError as e: raise ModelSchemaError('Kandidatenantwort verletzt das Datenschema; Lauf gestoppt.','discover',e) from e
    valid=[]
    for c in discovery.candidates[:request.max_candidates]:
        matching=[h for h in hits if h['id'] in c.discovery_source_ids]
        if matching and c.name.casefold() in ' '.join(h['title']+' '+h['snippet'] for h in matching).casefold(): valid.append(c)
    if not valid:
        return {'summary':'Keine ausreichend belegten neuen Kandidaten aus den Suchtreffern.','candidates':[],
                'sources':[],'discovery_hits':hits,'fetch_failures':[], 'usage':getattr(model,'usage',[]),'search_calls':getattr(search,'calls',0)}
    groups=[]
    for c in valid:
        start=len(hits)
        add_hits(f'"{c.name}" latest investor relations quarterly results free cash flow dividend {datetime.now(timezone.utc).year}')
        add_hits(f'"{c.name}" annual report risk factors debt capital expenditure official')
        relevant=hits[start:]+[x for x in hits if c.name.casefold() in (x['title']+' '+x['snippet']).casefold()]
        unique={x['url']:x for x in relevant}
        group=sorted(unique.values(),key=lambda x:(not is_primary(x['url']), 'results' not in x['url'].lower()))
        groups.append(group)
    # Round-robin avoids using the whole read budget for the first company.
    selected=[];seen=set()
    for i in range(max((len(g) for g in groups),default=0)):
        for group in groups:
            if i<len(group) and group[i]['url'] not in seen:
                selected.append(group[i]);seen.add(group[i]['url'])
    tick('read','Originaldokumente abrufen und lesbare Auszüge sichern')
    for hit in selected[:12]:
        tick('read',f'Originalquelle {len(originals)+len(failures)+1} von {min(len(selected),12)} lesen')
        try:
            s=fetch(hit['url'],title=hit['title'],sid=f'S{len(originals)+1:03}')
            originals.append(s)
        except Exception as e:
            failures.append({'url':hit['url'],'reason':str(e)[:180] if isinstance(e,ResearchError) else 'Dokument konnte nicht ausgewertet werden.'})
    if not originals: raise ResearchError('Keine Originalquelle lesbar. Suchsnippets werden nicht als geprüfte Finanzdaten ausgegeben.')
    public_sources=[{k:s[k] for k in ('id','title','url','text','retrieved_at','method','truncated','primary_domain')} for s in originals]
    tick('analyze','These, Dividendenqualität und Bewertungsfragen formulieren')
    try:
        result=Analysis.model_validate(model(ANALYZE,{'as_of':now(),'question':request.topic,
          'candidates':[c.model_dump() for c in valid],'sources':public_sources},Analysis.model_json_schema(),max_tokens=6000))
    except ValidationError as e: raise ModelSchemaError('Analyseantwort verletzt das Datenschema; keine fehlerhafte Analyse freigegeben.','analyze',e) from e
    allowed_names={x.name.casefold() for x in valid}
    candidates=[evidence_check(c.model_dump(),originals) for c in result.candidates if c.name.casefold() in allowed_names][:request.max_candidates]
    tick('challenge','Gegenthese und Belegkritik in einem zweiten Durchlauf prüfen')
    # Total calls = discovery + analysis + review. Never silently skip review on model error.
    try:
        review=Review.model_validate(model(REVIEW,{'analysis':candidates,'sources':public_sources},Review.model_json_schema(),max_tokens=3200))
    except ValidationError as e: raise ModelSchemaError('Gegenprüfung verletzt das Datenschema; keine vollständige Analyse freigegeben.','challenge',e) from e
    lookup={s['id']:s for s in originals}
    for c in candidates:
        r=next((x for x in review.reviews if x.name.casefold()==c['name'].casefold()),None)
        if not r:
            c['warnings'].append('Gegenprüfung für diesen Kandidaten fehlt.');c['verdict']='Daten fehlen'
            c['review']=None
        else:
            rd=r.model_dump(); invalid=[x for x in r.source_ids if x not in lookup]
            rd['source_ids']=[x for x in r.source_ids if x in lookup]
            if invalid: c['warnings'].append('Unbekannte Quellenreferenz in der Gegenprüfung entfernt.');c['verdict']='Daten fehlen'
            if r.unsupported_facts:
                c['warnings'].append('Die Gegenprüfung bestreitet mindestens eine Aussage; vor Verwendung manuell klären.')
                c['verdict']='Daten fehlen'
            c['review']=rd
            c['checks']['semantic_review']='Modell-Gegenprüfung erfolgt; nicht unabhängig und nicht manuell freigegeben'
        # Always distinguish source-backed research from price/eligibility decisions.
        c['open_questions']=list(dict.fromkeys(c['open_questions']+[
            'Aktuellen Kurs und Aktiengattung vor einer Preisentscheidung prüfen.',
            'Handelbarkeit im eigenen Trade-Republic-Firmendepot manuell bestätigen.'
        ]))
    tick('done','Recherche mit Quellenstand und Gegenprüfung abgeschlossen')
    return {'summary':result.summary,'candidates':candidates,'sources':originals,'discovery_hits':hits,
            'fetch_failures':failures,'usage':getattr(model,'usage',[]),'search_calls':getattr(search,'calls',0),
            'model_calls':getattr(model,'calls',0),'method_version':'0.3.0',
            'prompts_sha256':digest({'discovery':DISCOVER,'analysis':ANALYZE,'review':REVIEW}),
            'notice':'Research-Entwurf mit Modell-Gegenprüfung. Kein vollständig geprüfter Investmentrat. Originalauszüge, keine vollständige Due Diligence.'}
