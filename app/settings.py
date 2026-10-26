from __future__ import annotations
import json, os, tempfile
from pathlib import Path
from .models import ConnectionInput

class Settings:
    def __init__(self, root:Path, environment_only=False):
        self.path=root/'connections.private.json'
        self.environment_only=environment_only
    def raw(self):
        data={'provider':'bedrock','model_id':'','region':'eu-central-1','aws_profile':'','brave_key':'','anthropic_key':''}
        if not self.environment_only and self.path.exists(): data.update(json.loads(self.path.read_text()))
        for key,env in {'provider':'PIA_PROVIDER','model_id':'PIA_MODEL_ID','region':'PIA_AWS_REGION','aws_profile':'PIA_AWS_PROFILE','brave_key':'BRAVE_API_KEY','anthropic_key':'ANTHROPIC_API_KEY'}.items():
            if os.getenv(env): data[key]=os.environ[env]
        return data
    def save(self,values:ConnectionInput):
        if self.environment_only: raise ValueError('Hosted credentials are environment-only.')
        existing=json.loads(self.path.read_text()) if self.path.exists() else {}
        incoming=values.model_dump()
        if incoming.pop('clear_secrets'): existing.update(brave_key='',anthropic_key='')
        for k,v in incoming.items():
            if k.endswith('_key') and (v is None or not v.strip()): continue
            existing[k]=v
        fd,tmp=tempfile.mkstemp(dir=self.path.parent,prefix='.settings-')
        try:
            os.fchmod(fd,0o600)
            with os.fdopen(fd,'w') as f: json.dump(existing,f,ensure_ascii=False)
            os.replace(tmp,self.path)
        finally:
            if os.path.exists(tmp): os.unlink(tmp)
    def public(self):
        d=self.raw()
        missing=[]
        if not d['model_id']: missing.append('Modell-ID')
        if not d['brave_key']: missing.append('Brave-Suchschlüssel')
        if d['provider']=='anthropic' and not d['anthropic_key']: missing.append('Anthropic-Schlüssel')
        if d['provider']=='bedrock' and not d['region']: missing.append('AWS-Region')
        return {k:d[k] for k in ('provider','model_id','region','aws_profile')} | {
            'has_brave_key':bool(d['brave_key']),'has_anthropic_key':bool(d['anthropic_key']),
            'configured':not missing,'missing':missing,
            'managed_by_environment':self.environment_only,
            'verified':False,'notice':'Konfiguriert bedeutet noch nicht live getestet. AWS-Berechtigungen werden beim Aufruf geprüft.',
            'environment_overrides':bool(any(os.getenv(x) for x in ('PIA_PROVIDER','PIA_MODEL_ID','BRAVE_API_KEY','ANTHROPIC_API_KEY')))}
