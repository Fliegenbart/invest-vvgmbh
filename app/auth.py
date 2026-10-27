"""Browser form sign-in using the existing private-app credentials."""
from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
import time
from html import escape
from pathlib import Path
from urllib.parse import parse_qs

from fastapi import Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse

SESSION_COOKIE = '__Host-pia_session'
SESSION_TTL = 12 * 60 * 60
STATIC = Path(__file__).resolve().parents[1] / 'static'


def credentials_match(username: str, password: str) -> bool:
    expected = os.getenv('PIA_ACCESS_KEY', '')
    if len(expected) < 32:
        return False
    user_ok = secrets.compare_digest(username.encode(), os.getenv('PIA_USERNAME', 'pia').encode())
    password_ok = secrets.compare_digest(password.encode(), expected.encode())
    return user_ok and password_ok


def session_signature(payload: str) -> str:
    # Changing either configured credential invalidates existing browser sessions.
    material = 'pia-browser-session:' + os.getenv('PIA_USERNAME', 'pia') + ':' + os.getenv('PIA_ACCESS_KEY', '')
    key = hashlib.sha256(material.encode()).digest()
    return hmac.new(key, payload.encode(), hashlib.sha256).hexdigest()


def new_session() -> str:
    payload = f'{int(time.time()) + SESSION_TTL}.{secrets.token_hex(16)}'
    return payload + '.' + session_signature(payload)


def session_authorized(request: Request) -> bool:
    if len(os.getenv('PIA_ACCESS_KEY', '')) < 32:
        return False
    token = request.cookies.get(SESSION_COOKIE, '')
    if len(token) > 160 or not re.fullmatch(r'[0-9]{1,12}\.[0-9a-f]{32}\.[0-9a-f]{64}', token):
        return False
    expires, nonce, signature = token.split('.')
    if not hmac.compare_digest(signature, session_signature(expires + '.' + nonce)):
        return False
    remaining = int(expires) - time.time()
    return 0 < remaining <= SESSION_TTL + 60


def login_page(message: str = '', status_code: int = 200):
    html = (STATIC / 'login.html').read_text()
    error = f'<p class="login-error" role="alert">{escape(message)}</p>' if message else ''
    html = html.replace('<!--LOGIN_ERROR-->', error)
    html = html.replace('__USERNAME__', escape(os.getenv('PIA_USERNAME', 'pia'), quote=True))
    return HTMLResponse(html, status_code=status_code)


def install_browser_login(app):
    @app.get('/login', include_in_schema=False)
    def login(request: Request):
        if session_authorized(request):
            return RedirectResponse('/', status_code=303)
        return login_page()

    @app.get('/login.css', include_in_schema=False)
    def login_styles():
        return FileResponse(STATIC / 'login.css', media_type='text/css')

    @app.post('/login', include_in_schema=False)
    async def sign_in(request: Request):
        expected_origin = 'https://' + request.url.netloc
        if request.headers.get('origin') != expected_origin:
            return login_page('Bitte die Anmeldung auf dieser Seite erneut öffnen.', 403)
        if request.headers.get('content-type', '').split(';')[0].strip().lower() != 'application/x-www-form-urlencoded':
            return login_page('Bitte das Anmeldeformular verwenden.', 415)
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > 4096:
                return login_page('Die Eingabe ist zu lang.', 413)
        try:
            values = parse_qs(body.decode('utf-8'), keep_blank_values=True,
                              strict_parsing=True, max_num_fields=2)
            if set(values) != {'username', 'password'} or any(len(v) != 1 for v in values.values()):
                raise ValueError('Invalid fields')
            username, password = values['username'][0], values['password'][0]
        except (ValueError, UnicodeError):
            return login_page('Bitte Benutzername und Passwort erneut eingeben.', 400)
        if not credentials_match(username, password):
            return login_page('Benutzername oder Passwort stimmt nicht. Bitte erneut versuchen.', 401)
        response = RedirectResponse('/', status_code=303)
        response.set_cookie(SESSION_COOKIE, new_session(), max_age=SESSION_TTL,
                            secure=True, httponly=True, samesite='strict', path='/')
        return response

    @app.post('/api/logout', include_in_schema=False)
    def sign_out():
        from fastapi.responses import JSONResponse
        response = JSONResponse({'ok': True})
        response.delete_cookie(SESSION_COOKIE, path='/', secure=True, httponly=True, samesite='strict')
        return response
