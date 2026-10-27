"""Private Vercel deployment: HTTP authentication and durable PostgreSQL storage.

All database and provider credentials are supplied by the deployment environment.
Never fall back to an ephemeral SQLite database when hosted storage is unavailable.
"""
from __future__ import annotations
import base64
import json
import os
import secrets
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from .models import Mandate
from .storage import Store, SEEDS, canonical, digest, now


def cloud_authorized(request):
    from .auth import credentials_match, session_authorized
    if session_authorized(request):
        return True
    try:
        scheme, encoded = request.headers.get('authorization', '').split(' ', 1)
        if scheme.lower() != 'basic':
            return False
        user, password = base64.b64decode(encoded, validate=True).decode('utf-8').split(':', 1)
    except (ValueError, UnicodeError):
        return False
    return credentials_match(user, password)


def setup_app(missing):
    """Fail closed, with no financial or credential content in the public response."""
    from html import escape
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    @app.get('/api/health')
    def health():
        return JSONResponse({'ok':False, 'mode':'setup_required', 'version':'0.4.0'}, status_code=503)
    @app.api_route('/{path:path}', methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH'])
    def setup(path: str):
        items = ''.join('<li>' + escape(item) + '</li>' for item in missing)
        return HTMLResponse('<!doctype html><html lang="de"><meta charset="utf-8">'
          '<meta name="viewport" content="width=device-width,initial-scale=1">'
          '<title>PIA · Einrichtung</title><body><main><h1>PIA ist noch gesperrt.</h1>'
          '<p>In den Vercel-Projekteinstellungen fehlen noch folgende Konfigurationen:</p>'
          '<ul>' + items + '</ul><p>Ein PostgreSQL-Datenbankanschluss und ein langer, zufälliger '
          'Zugangsschlüssel sind erforderlich. Nach dem Hinterlegen neu deployen.</p>'
          '<p>Bis dahin werden keine Finanzdaten oder API-Schlüssel öffentlich bereitgestellt.</p>'
          '</main></body></html>', status_code=503,
          headers={'Cache-Control':'no-store', 'X-Content-Type-Options':'nosniff',
                   'Content-Security-Policy':"default-src 'none'; frame-ancestors 'none'; base-uri 'none'"})
    return app


class PostgresStore(Store):
    """API-compatible storage. Transactions serialize hash journal and research claims."""
    def __init__(self, url):
        self.url = url
        self.lock = threading.RLock()
        with self.db() as db:
            db.execute('SELECT pg_advisory_xact_lock(74189001)')
            db.execute('''CREATE TABLE IF NOT EXISTS pia_kv (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS pia_watch (seq BIGSERIAL UNIQUE, id TEXT PRIMARY KEY, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS pia_runs (seq BIGSERIAL UNIQUE, id TEXT PRIMARY KEY, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS pia_events (seq BIGSERIAL PRIMARY KEY, payload TEXT NOT NULL, prev_hash TEXT NOT NULL, hash TEXT NOT NULL);''')
            db.execute('SELECT pg_advisory_xact_lock(74189001)')
            db.execute('INSERT INTO pia_kv VALUES (%s,%s) ON CONFLICT DO NOTHING',
                       ('mandate', canonical(Mandate().model_dump(mode='json'))))
            seeded = db.execute('SELECT value FROM pia_kv WHERE key=%s', ('seeded',)).fetchone()
            if not seeded:
                for item in SEEDS:
                    payload = dict(item, id=uuid.uuid4().hex[:16], updated_at=now(), instrument='',
                                   broker_status='Ungeprüft', note='Recherchewunsch, keine vorhandene Position.')
                    db.execute('INSERT INTO pia_watch(id,payload) VALUES (%s,%s)', (payload['id'], canonical(payload)))
                db.execute('INSERT INTO pia_kv VALUES (%s,%s)', ('seeded', 'true'))

    @contextmanager
    def db(self):
        import psycopg
        with psycopg.connect(self.url, connect_timeout=10) as db:
            db.execute("SET LOCAL statement_timeout = '15s'")
            db.execute("SET LOCAL lock_timeout = '10s'")
            yield db

    def get(self, key, default=None):
        with self.db() as db:
            row = db.execute('SELECT value FROM pia_kv WHERE key=%s', (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def set(self, key, value):
        with self.db() as db:
            db.execute('INSERT INTO pia_kv VALUES (%s,%s) ON CONFLICT(key) DO UPDATE SET value=EXCLUDED.value', (key, canonical(value)))

    def watchlist(self):
        with self.db() as db:
            rows = db.execute('SELECT payload FROM pia_watch ORDER BY seq').fetchall()
        return [json.loads(row[0]) for row in rows]

    def save_watch(self, payload, item_id=None, journal=True):
        with self.db() as db:
            db.execute('SELECT pg_advisory_xact_lock(74189002)')
            if not item_id:
                rows = db.execute('SELECT payload FROM pia_watch').fetchall()
                old = next((json.loads(row[0]) for row in rows if json.loads(row[0])['name'].casefold() == payload['name'].casefold()), None)
                if old:
                    return old
            payload = dict(payload, id=item_id or uuid.uuid4().hex[:16], updated_at=now())
            db.execute('INSERT INTO pia_watch(id,payload) VALUES (%s,%s) ON CONFLICT(id) DO UPDATE SET payload=EXCLUDED.payload',
                       (payload['id'], canonical(payload)))
        if journal:
            self.event('watch_updated', {'id':payload['id'], 'name':payload['name']})
        return payload

    def delete_watch(self, item_id):
        with self.db() as db:
            db.execute('DELETE FROM pia_watch WHERE id=%s', (item_id,))
        self.event('watch_removed', {'id':item_id})

    def save_run(self, run):
        with self.db() as db:
            db.execute('INSERT INTO pia_runs(id,payload) VALUES (%s,%s) ON CONFLICT(id) DO UPDATE SET payload=EXCLUDED.payload',
                       (run['id'], canonical(run)))

    def run(self, rid):
        with self.db() as db:
            row = db.execute('SELECT payload FROM pia_runs WHERE id=%s', (rid,)).fetchone()
        return json.loads(row[0]) if row else None

    def runs(self):
        with self.db() as db:
            rows = db.execute('SELECT payload FROM pia_runs ORDER BY seq DESC LIMIT 100').fetchall()
        return [json.loads(row[0]) for row in rows]

    def event(self, kind, data):
        with self.db() as db:
            db.execute('SELECT pg_advisory_xact_lock(74189003)')
            row = db.execute('SELECT hash FROM pia_events ORDER BY seq DESC LIMIT 1').fetchone()
            prev = row[0] if row else '0' * 64
            payload = {'at':now(), 'kind':kind, 'data':data}
            hashed = digest({'previous':prev, 'payload':payload})
            db.execute('INSERT INTO pia_events(payload,prev_hash,hash) VALUES (%s,%s,%s)', (canonical(payload), prev, hashed))
        return hashed

    def events(self):
        with self.db() as db:
            rows = db.execute('SELECT seq,payload,prev_hash,hash FROM pia_events ORDER BY seq').fetchall()
        return [{'seq':r[0], 'payload':json.loads(r[1]), 'previous':r[2], 'hash':r[3]} for r in rows]

    def integrity(self):
        return super().integrity() | {'notice':'Hash-Kette in PostgreSQL; kein externer Zeitstempel. Kopf-Hash separat aufbewahren.'}

    def _active(self, db):
        # The six-minute lease is longer than Vercel's configured five-minute request cap.
        rows = db.execute("SELECT id,payload FROM pia_runs WHERE payload::jsonb->>'status' IN ('queued','running') FOR UPDATE").fetchall()
        active = []
        for rid, raw in rows:
            run = json.loads(raw)
            start = datetime.fromisoformat(run.get('started_at', run['created_at']))
            if (datetime.now(timezone.utc) - start).total_seconds() > 360:
                run.update(status='interrupted', finished_at=now(), message='Zeitlimit oder Verbindungsabbruch. Kein automatischer kostenpflichtiger Neustart.')
                db.execute('UPDATE pia_runs SET payload=%s WHERE id=%s', (canonical(run), rid))
            else:
                active.append(run)
        return active

    def expire_runs(self):
        with self.db() as db:
            db.execute('SELECT pg_advisory_xact_lock(74189004)')
            self._active(db)

    def claim_run(self, run):
        with self.db() as db:
            db.execute('SELECT pg_advisory_xact_lock(74189004)')
            if self._active(db):
                return False
            db.execute('INSERT INTO pia_runs(id,payload) VALUES (%s,%s)', (run['id'], canonical(run)))
        return True

    def begin_run(self, rid):
        with self.db() as db:
            db.execute('SELECT pg_advisory_xact_lock(74189004)')
            self._active(db)
            row = db.execute('SELECT payload FROM pia_runs WHERE id=%s FOR UPDATE', (rid,)).fetchone()
            if not row:
                return None
            run = json.loads(row[0])
            if run['status'] != 'queued':
                return None
            run.update(status='running', started_at=now())
            db.execute('UPDATE pia_runs SET payload=%s WHERE id=%s', (canonical(run), rid))
        return run


def cloud_store(url):
    return PostgresStore(url)
