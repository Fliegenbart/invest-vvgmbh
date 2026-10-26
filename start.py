#!/usr/bin/env python3
"""Start the personal PIA server on loopback; never deploy this unauthenticated app publicly."""
import os,sys,threading,webbrowser
from pathlib import Path
if sys.version_info<(3,11):
    raise SystemExit('PIA benötigt Python 3.11 oder neuer.')
os.chdir(Path(__file__).resolve().parent)
os.umask(0o077)
PORT=int(os.getenv('PIA_PORT','8765'))
if __name__=='__main__':
    if '--no-browser' not in sys.argv:
        threading.Timer(1.8,lambda:webbrowser.open(f'http://127.0.0.1:{PORT}')).start()
    import uvicorn
    print(f'\nPIA läuft lokal unter http://127.0.0.1:{PORT}\nBeenden: Ctrl+C.\n')
    uvicorn.run('app.main:app',host='127.0.0.1',port=PORT,log_level='warning',access_log=False)
