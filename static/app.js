import {shell,watch,watchForm,valuationForm} from './views.js';
import {esc,euro,icon,modal,toast,themes} from './ui.js';
const state={page:'research',mandate:{},watchlist:[],runs:[],connection:{},activeRun:null,journal:null,draftTopic:'',watchFilter:''};
let csrf='',pollTimer;
async function api(path,method='GET',body){
 const r=await fetch('/api'+path,{method,headers:{'Content-Type':'application/json','X-PIA-Token':csrf},...(body===undefined?{}:{body:JSON.stringify(body)})});
 if(r.status===401){window.location.replace('/login');throw new Error('Bitte erneut anmelden.');}
 const data=await r.json().catch(()=>({detail:'Keine gültige Antwort vom lokalen Server.'}));
 if(!r.ok)throw new Error(typeof data.detail==='string'?data.detail:'Eingaben oder Verbindung prüfen.');
 return data;
}
async function refresh(){const b=await api('/bootstrap');csrf=b.csrf;Object.assign(state,b);}
function render(){document.querySelector('#app').innerHTML=shell(state,state.page);}
function page(){const p=location.hash.slice(1);return ['research','watch','journal','mandate','settings'].includes(p)?p:'research';}
async function route(){state.page=page();render();if(state.page==='journal'){state.journal=await api('/journal');render();}}
function go(p){if(location.hash==='#'+p){state.page=p;render();}else location.hash=p;}
async function loadRun(id){state.activeRun=await api('/runs/'+encodeURIComponent(id));go('research');render();if(['queued','running'].includes(state.activeRun.status))schedulePoll(id);}
function schedulePoll(id){clearTimeout(pollTimer);pollTimer=setTimeout(async()=>{try{const r=await api('/runs/'+id);if(state.activeRun?.id===id){state.activeRun=r;if(state.page==='research')render();}if(['queued','running'].includes(r.status))schedulePoll(id);else {await refresh();if(state.page==='research')render();}}catch(e){toast(e.message,true);}},1400);}
function closeModal(){document.querySelector('dialog')?.close();document.querySelector('dialog')?.remove();}
const presets={
 china:'Finde chinesische KI-Unternehmen mit belastbarer Ertragskraft und nachvollziehbarer Bewertung. Prüfe Tencent, Alibaba und Baidu kritisch und suche auch weniger offensichtliche Alternativen.',
 dividend:'Finde langfristig interessante Dividendenunternehmen weltweit. Prüfe freien Cashflow, Ausschüttungsdeckung, Verschuldung und Bewertung; keine reine Jagd nach hoher Dividendenrendite.',
 space:'Untersuche SpaceX und weitere Raumfahrt-Unternehmen: aktuelle Aktiengattung, Börsennotierung, Finanzierung, Wettbewerb und Bewertung. Keine Handelbarkeit im Trade-Republic-Depot unterstellen.'
};
document.addEventListener('click',async e=>{
 const preset=e.target.closest('[data-preset]');
 if(preset){const t=document.querySelector('#research-topic');t.value=presets[preset.dataset.preset];state.draftTopic=t.value;return;}
 const btn=e.target.closest('[data-action]');if(!btn)return;
 const action=btn.dataset.action,id=btn.dataset.id;
 try{
  if(action==='logout'){await api('/logout','POST',{});window.location.replace('/login');return;}
  if(action==='close-dialog'){closeModal();return;}
  if(action==='go-settings'){go('settings');return;}
  if(action==='back-research'){state.activeRun=null;render();return;}
  if(action==='demo'){btn.disabled=true;const r=await api('/demo','POST',{});await refresh();state.activeRun=r;go('research');render();return;}
  if(action==='open-run'){await loadRun(id);return;}
  if(action==='cancel-run'){await api('/runs/'+id+'/cancel','POST',{});toast('Abbruch vorgemerkt.');return;}
  if(action==='add-watch'){modal('Unternehmen hinzufügen',watchForm());return;}
  if(action==='edit-watch'){modal('Recherchewunsch bearbeiten',watchForm(state.watchlist.find(x=>x.id===id)));return;}
  if(action==='research-watch'){
   const w=state.watchlist.find(x=>x.id===id);state.activeRun=null;state.draftTopic=`Untersuche ${w.name} als langfristige Anlage. ${w.question} Prüfe Originalquellen, Dividendenqualität, Bewertung und die stärkste Gegenthese.`.slice(0,400);state.draftThemes=[w.theme];state.draftMode='company';go('research');render();document.querySelector('#research-topic')?.focus();return;
  }
  if(action==='delete-watch'){
   if(!confirm('Diesen Recherchewunsch aus der Watchlist entfernen? Das Journal bleibt erhalten.'))return;
   await api('/watchlist/'+id,'DELETE');closeModal();await refresh();render();toast('Aus Watchlist entfernt.');return;
  }
  if(action==='calc-watch'){modal('Bewertung nachvollziehbar rechnen',valuationForm(state.watchlist.find(x=>x.id===id)),true);return;}
  if(action==='save-candidate'){
   const c=state.activeRun.result.candidates[Number(btn.dataset.index)];
   await api('/watchlist','POST',{name:c.name,theme:c.theme,question:c.thesis.slice(0,1200),instrument:c.instrument,broker_status:'Ungeprüft',note:'Aus Recherche '+state.activeRun.id+' übernommen. Keine Kaufentscheidung.'});
   await refresh();toast('In der Watchlist gespeichert.');return;
  }
  if(action==='decision-candidate'){
   const c=state.activeRun.result.candidates[Number(btn.dataset.index)];
   modal('Entscheidung dokumentieren',`<form id="decision-form"><input type="hidden" name="name" value="${esc(c.name)}"><input type="hidden" name="run_id" value="${state.activeRun.id}"><p class="dialog-intro">${esc(c.name)}${state.activeRun.is_demo?' · Synthetisches Bedienbeispiel':''}</p><label class="field"><span>Entscheidung</span><select name="decision"><option>Beobachten</option><option>Vertieft prüfen</option><option>Verwerfen</option><option>Eigene Entscheidung dokumentiert</option></select></label><label class="field"><span>Warum? Was würde deine Meinung ändern?</span><textarea name="note" required minlength="3" maxlength="4000" rows="4"></textarea></label><p class="field-hint">Nur eine Notiz. Keine Order wird übermittelt.</p><button type="submit" class="button primary">Im Journal speichern ${icon('journal')}</button></form>`);return;
  }
  if(action==='test-connection'){
   btn.disabled=true;btn.textContent='Verbindung wird geprüft …';const r=await api('/connections/test','POST',{});
   document.querySelector('#connection-result').innerHTML=`<div class="notice ${r.ok?'':'amber'}"><strong>${r.ok?'Verbindung erfolgreich geprüft':'Verbindung noch nicht einsatzbereit'}</strong><p>Suche: ${esc(r.search)}</p><p>Modell: ${esc(r.model)}</p></div>`;return;
  }
  if(action==='clear-secrets'){
   if(!confirm('Die lokal hinterlegten API-Schlüssel löschen? Umgebungsvariablen bleiben unverändert.'))return;
   await api('/connections','PUT',{provider:state.connection.provider,model_id:state.connection.model_id,region:state.connection.region,aws_profile:state.connection.aws_profile,clear_secrets:true});await refresh();render();toast('Lokale Schlüssel gelöscht.');return;
  }
  if(action==='copy-hash'){
   const h=state.journal?.integrity?.head||state.integrity.head;await navigator.clipboard.writeText(h);toast('Kopf-Hash kopiert. Separat vertrauenswürdig aufbewahren.');return;
  }
 }catch(err){toast(err.message,true);}finally{if(btn.isConnected){btn.disabled=false;if(action==='test-connection')btn.textContent='Verbindung testen';}}
});
document.addEventListener('input',e=>{
 if(e.target.id==='research-topic')state.draftTopic=e.target.value;
 if(e.target.id==='watch-filter'){
  state.watchFilter=e.target.value;
  const tmp=document.createElement('div');tmp.innerHTML=watch(state);
  document.querySelector('#watch-rows').innerHTML=tmp.querySelector('#watch-rows').innerHTML;
  document.querySelector('.watch-toolbar>span').textContent=tmp.querySelector('.watch-toolbar>span').textContent;
 }
});
document.addEventListener('change',e=>{
 if(e.target.id==='provider-select'){
  document.querySelectorAll('.bedrock-fields').forEach(x=>x.classList.toggle('hidden',e.target.value!=='bedrock'));
  document.querySelectorAll('.anthropic-fields').forEach(x=>x.classList.toggle('hidden',e.target.value!=='anthropic'));
 }
});
document.addEventListener('submit',async e=>{
 const form=e.target;if(!form.id)return;e.preventDefault();
 const f=new FormData(form),data=Object.fromEntries(f.entries()),button=form.querySelector('button[type="submit"]');
 if(button)button.disabled=true;
 try{
  if(form.id==='research-form'){
   const selected=f.getAll('themes');if(!selected.length)throw new Error('Mindestens eine Suchrichtung auswählen.');
   if(!state.connection.configured){go('settings');throw new Error('Für echte Recherche zuerst Modell und Brave-Suche verbinden.');}
   const r=await api('/research','POST',{topic:data.topic,themes:selected,max_candidates:Number(data.max_candidates),mode:state.draftMode||'discover'});
   state.activeRun=r;render();schedulePoll(r.id);
   if(r.execution_mode==='request'){
    api('/runs/'+encodeURIComponent(r.id)+'/execute','POST',{}).catch(err=>toast(err.message,true));
   }
  }else if(form.id==='watch-form'){
   const id=form.dataset.id;await api('/watchlist'+(id?'/'+id:''),id?'PUT':'POST',data);closeModal();await refresh();render();toast('Watchlist gespeichert.');
  }else if(form.id==='mandate-form'){
   await api('/mandate','PUT',{...state.mandate,...data,capital:Number(data.capital),contribution:Number(data.contribution),interval_months:Number(data.interval_months),reserve_confirmed:f.has('reserve_confirmed')});await refresh();render();toast('Anlagemandat gespeichert.');
  }else if(form.id==='settings-form'){
   const c=await api('/connections','PUT',{...data,brave_key:data.brave_key||null,anthropic_key:data.anthropic_key||null,clear_secrets:false});state.connection=c;render();toast('Verbindungen gespeichert. Ein Live-Test bestätigt den Zugang.');
  }else if(form.id==='decision-form'){
   await api('/decisions','POST',data);closeModal();toast('Entscheidung im Journal gespeichert.');
  }else if(form.id==='valuation-form'){
   const r=await api('/valuation','POST',{...data,as_of:new Date(data.as_of).toISOString(),price:data.price,eps:data.eps===''?null:data.eps,dividend_per_share:data.dividend_per_share===''?null:data.dividend_per_share});
   document.querySelector('#valuation-result').innerHTML=`<div class="valuation-result"><div><span>Kurs-Gewinn-Verhältnis</span><strong>${esc(r.pe??'–')}</strong></div><div><span>Bruttodividendenrendite</span><strong>${r.gross_dividend_yield_pct===null?'–':esc(r.gross_dividend_yield_pct)+' %'}</strong></div></div>${r.stale?'<div class="notice amber">Der eingegebene Kurs ist älter als 72 Stunden. Keine aktuelle Preisbewertung ableiten.</div>':''}<p class="field-hint">${esc(r.notice)}</p>`;toast('Berechnung im Journal dokumentiert.');
  }
 }catch(err){toast(err.message,true);}finally{if(button?.isConnected)button.disabled=false;}
});
window.addEventListener('hashchange',()=>route().catch(e=>toast(e.message,true)));
try{await refresh();await route();}catch(e){document.querySelector('#app').innerHTML=`<main class="loading-screen"><div class="brand-letter">p.</div><h1>Lokalen Server starten.</h1><p>${esc(e.message)}</p><p>PIA über START_MAC.command oder <code>python start.py</code> öffnen.</p></main>`;}
