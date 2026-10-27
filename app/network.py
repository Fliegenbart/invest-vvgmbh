"""Public HTTPS reader: no local IPs, no credentials, bounded downloads, pinned DNS."""
from __future__ import annotations
import hashlib, http.client, ipaddress, io, re, socket, ssl
from urllib.parse import urlsplit, urlunsplit, urljoin
from bs4 import BeautifulSoup
from pypdf import PdfReader
from .budget import timeout

class ResearchError(ValueError): pass


class ModelSchemaError(ResearchError):
    """Bounded schema diagnostics without raw model output or invalid input values."""
    def __init__(self, message, stage, error):
        super().__init__(message)
        self.stage = stage
        self.issues = []
        for issue in error.errors(include_input=False, include_url=False)[:10]:
            location = list(issue['loc'])
            if issue['type'] == 'extra_forbidden' and location:
                location[-1] = '<extra>'
            self.issues.append({'field': '.'.join(map(str, location))[:160], 'code': issue['type']})

MAX_BYTES=6_000_000
# Explicit, inspectable starting registry. Unknown issuer domains are not silently trusted.
PRIMARY_DOMAINS={
 'tencent.com','alibabagroup.com','baidu.com','spacex.com','sec.gov','hkexnews.hk','hkex.com.hk','nasdaq.com',
 'allianz.com','munichre.com','siemens.com','schneider-electric.com','se.com','ibm.com','microsoft.com','apple.com',
 'alphabet.com','abc.xyz','investor.nvidia.com','nvidia.com','tsmc.com','asml.com','samsung.com','sse.com.cn','szse.cn',
 'investors.abb.com','abb.com','unilever.com','nestle.com','jnj.com','pg.com','coca-colacompany.com',
 'berkshirehathaway.com','lvmh.com','sanofi.com','novonordisk.com','shell.com','totalenergies.com','rio-tinto.com','riotinto.com',
 'vanguard.com','vanguard.co.uk','ishares.com','blackrock.com','amundietf.com','dws.com','bmwgroup.com','mercedes-benz.com',
 'deutsche-boerse.com','londonstockexchange.com','euronext.com','investors.comcast.com','investor.visa.com',
 'corporate.visa.com','mastercard.com','broadcom.com','netflix.net','meta.com','aboutamazon.com','amazon.com',
 'bookingholdings.com','adobe.com','sap.com','linde.com','deutschepost.de','group.dhl.com','dhl.com','hkexgroup.com',
}

def normalize_text(text): return re.sub(r'\s+',' ',text).strip()
def host_of(url): return (urlsplit(url).hostname or '').lower()
def is_primary(url):
    h=host_of(url)
    return any(h==x or h.endswith('.'+x) for x in PRIMARY_DOMAINS)
def clean_url(url):
    try:
        p=urlsplit(url)
        if p.scheme!='https' or not p.hostname or p.username or p.password or p.port not in (None,443): raise ValueError()
        host=p.hostname.encode('idna').decode('ascii')
        if any(c in url for c in ('\r','\n','\x00')) or len(url)>3000: raise ValueError()
        return urlunsplit(('https',host,p.path or '/',p.query,''))
    except (ValueError,UnicodeError): raise ResearchError('Nur öffentliche HTTPS-Adressen ohne Zugangsdaten sind erlaubt.')

def public_addresses(host):
    try: addresses=list(dict.fromkeys(r[4][0] for r in socket.getaddrinfo(host,443,type=socket.SOCK_STREAM)))
    except OSError as e: raise ResearchError('Quellendomain nicht auflösbar.') from e
    if not addresses or any(not ipaddress.ip_address(a).is_global for a in addresses):
        raise ResearchError('Lokale, private oder reservierte Netzwerkadressen sind gesperrt.')
    return addresses

class PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self,host,address):
        super().__init__(host,timeout=timeout(15),context=ssl.create_default_context())
        self.address=address
    def connect(self):
        raw=socket.create_connection((self.address,443),self.timeout)
        self.sock=self._context.wrap_socket(raw,server_hostname=self.host)

def download_public(url):
    url=clean_url(url)
    for _ in range(4):
        p=urlsplit(url)
        address=public_addresses(p.hostname)[0]
        conn=PinnedHTTPSConnection(p.hostname,address)
        try:
            conn.request('GET',urlunsplit(('','',p.path,p.query,'')),headers={
                'User-Agent':'PIAResearch/0.3 (personal research; no automated trading)',
                'Accept':'text/html,application/pdf,text/plain','Accept-Encoding':'identity'})
            response=conn.getresponse()
            if response.status in (301,302,303,307,308):
                location=response.getheader('Location')
                if not location: raise ResearchError('Weiterleitung ohne Ziel.')
                url=clean_url(urljoin(url,location)); continue
            if response.status!=200: raise ResearchError(f'Originalquelle antwortet mit HTTP {response.status}.')
            length=response.getheader('Content-Length')
            if length and int(length)>MAX_BYTES: raise ResearchError('Originalquelle überschreitet 6 MB.')
            content=response.read(MAX_BYTES+1)
            if len(content)>MAX_BYTES: raise ResearchError('Originalquelle überschreitet 6 MB.')
            return url,response.getheader('Content-Type',''),content
        except (OSError,http.client.HTTPException,ValueError) as e:
            if isinstance(e,ResearchError): raise
            raise ResearchError('Originalquelle konnte nicht sicher abgerufen werden.') from e
        finally: conn.close()
    raise ResearchError('Zu viele Weiterleitungen.')

def extract_document(content_type,content):
    if 'pdf' in content_type or content.startswith(b'%PDF'):
        reader=PdfReader(io.BytesIO(content))
        if reader.is_encrypted: raise ResearchError('Verschlüsseltes PDF wird nicht ausgewertet.')
        if len(reader.pages)>350: raise ResearchError('PDF zu umfangreich (maximal 350 Seiten).')
        pages=[]
        for n,p in enumerate(reader.pages[:80]):
            pages.append(f'[Seite {n+1}] '+(p.extract_text() or ''))
            if sum(map(len,pages))>200_000: break
        return '\n'.join(pages),'PDF-Textauszug; Tabellen/Grafiken nicht visuell geprüft; höchstens 80 Seiten.'
    if 'html' in content_type:
        soup=BeautifulSoup(content,'html.parser')
        for node in soup(['script','style','noscript','nav','footer','header','form','svg']): node.decompose()
        return soup.get_text(' ',strip=True),'HTML-Textauszug; dynamische Inhalte können fehlen.'
    if 'text/plain' in content_type:
        return content.decode('utf-8',errors='replace'),'Textauszug'
    raise ResearchError('Nicht unterstütztes Dokumentformat.')

def select_excerpt(text,max_chars=16000):
    text=normalize_text(text)
    if len(text)<=max_chars: return text,False
    # Keep beginning and passages most likely to contain results/risks. Never call this a full read.
    terms=re.compile(r'cash flow|cashflow|dividend|revenue|capital expenditure|risk factor|earnings per share|net income|share repurchase|net debt|operating profit',re.I)
    spans=[(0,5000)]
    for m in terms.finditer(text):
        start,end=max(0,m.start()-450),min(len(text),m.end()+1000)
        if not any(start<b and end>a for a,b in spans): spans.append((start,end))
        if sum(b-a for a,b in spans)>max_chars-1000: break
    out='\n[Auszugslücke]\n'.join(text[a:b] for a,b in sorted(spans))[:max_chars]
    return out,True

def fetch_source(url,title='',sid=''):
    from .storage import now
    url,ctype,body=download_public(url)
    text,method=extract_document(ctype,body)
    if len(normalize_text(text))<120: raise ResearchError('Kein ausreichender lesbarer Originaltext; kein Beleg übernommen.')
    excerpt,truncated=select_excerpt(text)
    return {'id':sid,'url':url,'title':title or host_of(url),'domain':host_of(url),'text':excerpt,
            'primary_domain':is_primary(url),'retrieved_at':now(),'document_sha256':hashlib.sha256(body).hexdigest(),
            'excerpt_sha256':hashlib.sha256(excerpt.encode()).hexdigest(),'method':method,'truncated':truncated,
            'evidence':'Originaltextauszug','content_type':ctype}
