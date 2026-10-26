from __future__ import annotations
import hashlib, json, os, sqlite3, threading, uuid
from datetime import datetime, timezone
from pathlib import Path
from contextlib import contextmanager
from .models import Mandate

def now(): return datetime.now(timezone.utc).isoformat()
def canonical(obj): return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)
def digest(obj): return hashlib.sha256(canonical(obj).encode()).hexdigest()

SEEDS = [
    {'name':'Tencent','theme':'KI & Wachstum','question':'Werden KI-Investitionen zu nachhaltig höherem freien Cashflow?'},
    {'name':'Alibaba','theme':'KI & Wachstum','question':'Wie viel Cloud-Wachstum bleibt nach Investitionen und Wettbewerb übrig?'},
    {'name':'Baidu','theme':'KI & Wachstum','question':'Können die neuen Geschäfte die Entwicklung des bisherigen Kerngeschäfts ausgleichen?'},
    {'name':'SpaceX','theme':'Chancen','question':'Aktuelles Instrument, Finanzierung, Bewertung und tatsächliche Verfügbarkeit im Firmendepot prüfen.'},
]

class Store:
    def __init__(self, root: Path):
        self.root = root
        root.mkdir(parents=True,exist_ok=True)
        try: root.chmod(0o700)
        except OSError: pass
        self.path = root/'pia.sqlite3'
        self.lock = threading.RLock()
        with self.db() as db:
            db.executescript('''CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS watch (id TEXT PRIMARY KEY, payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS events (seq INTEGER PRIMARY KEY AUTOINCREMENT, payload TEXT NOT NULL, prev_hash TEXT NOT NULL, hash TEXT NOT NULL);''')
        try: self.path.chmod(0o600)
        except OSError: pass
        if self.get('mandate') is None: self.set('mandate',Mandate().model_dump(mode='json'))
        if not self.get('seeded'):
            for x in SEEDS:
                self.save_watch(dict(x,instrument='',broker_status='Ungeprüft',note='Recherchewunsch, keine vorhandene Position.'), journal=False)
            self.set('seeded', True)
    @contextmanager
    def db(self):
        c=sqlite3.connect(self.path,timeout=15)
        try:
            c.execute('PRAGMA journal_mode=WAL')
            yield c
            c.commit()
        except BaseException:
            c.rollback()
            raise
        finally:
            c.close()
    def get(self,key,default=None):
        with self.db() as db: row=db.execute('SELECT value FROM kv WHERE key=?',(key,)).fetchone()
        return json.loads(row[0]) if row else default
    def set(self,key,value):
        with self.lock, self.db() as db: db.execute('INSERT OR REPLACE INTO kv VALUES (?,?)',(key,canonical(value)))
    def watchlist(self):
        with self.db() as db: rows=db.execute('SELECT payload FROM watch ORDER BY rowid').fetchall()
        return [json.loads(x[0]) for x in rows]
    def save_watch(self, payload, item_id=None, journal=True):
        with self.lock:
            if not item_id:
                # Name-level deduplication only; no inferred share-class equality.
                old=next((x for x in self.watchlist() if x['name'].casefold()==payload['name'].casefold()),None)
                if old: return old
            payload=dict(payload,id=item_id or uuid.uuid4().hex[:16],updated_at=now())
            with self.db() as db: db.execute('INSERT OR REPLACE INTO watch VALUES (?,?)',(payload['id'],canonical(payload)))
            if journal: self.event('watch_updated',{'id':payload['id'],'name':payload['name']})
        return payload
    def delete_watch(self,item_id):
        with self.lock, self.db() as db: db.execute('DELETE FROM watch WHERE id=?',(item_id,))
        self.event('watch_removed',{'id':item_id})
    def save_run(self, run):
        with self.lock, self.db() as db: db.execute('INSERT OR REPLACE INTO runs VALUES (?,?)',(run['id'],canonical(run)))
    def run(self,rid):
        with self.db() as db: row=db.execute('SELECT payload FROM runs WHERE id=?',(rid,)).fetchone()
        return json.loads(row[0]) if row else None
    def runs(self):
        with self.db() as db: rows=db.execute('SELECT payload FROM runs ORDER BY rowid DESC LIMIT 100').fetchall()
        return [json.loads(r[0]) for r in rows]
    def event(self,kind,data):
        with self.lock,self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT hash FROM events ORDER BY seq DESC LIMIT 1').fetchone()
            prev=row[0] if row else '0'*64
            payload={'at':now(),'kind':kind,'data':data}
            h=digest({'previous':prev,'payload':payload})
            db.execute('INSERT INTO events(payload,prev_hash,hash) VALUES (?,?,?)',(canonical(payload),prev,h))
        return h
    def events(self):
        with self.db() as db: rows=db.execute('SELECT seq,payload,prev_hash,hash FROM events ORDER BY seq').fetchall()
        return [{'seq':r[0],'payload':json.loads(r[1]),'previous':r[2],'hash':r[3]} for r in rows]
    def integrity(self):
        prev='0'*64
        events=self.events()
        for e in events:
            if e['previous']!=prev or e['hash']!=digest({'previous':prev,'payload':e['payload']}):
                return {'ok':False,'first_bad_event':e['seq'],'head':prev,'events':len(events)}
            prev=e['hash']
        return {'ok':True,'head':prev,'events':len(events),'notice':'Lokale Hash-Kette; kein externer Zeitstempel. Kopf-Hash separat aufbewahren.'}
