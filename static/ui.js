export const esc = (v) => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
export const euro = v => new Intl.NumberFormat('de-DE',{style:'currency',currency:'EUR',maximumFractionDigits:0}).format(Number(v || 0));
export const date = v => v ? new Date(v).toLocaleString('de-DE',{day:'2-digit',month:'short',year:'numeric',hour:'2-digit',minute:'2-digit'}) : '–';
const paths = {
 search:'<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 4 4"/>',
 radar:'<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><path d="m12 12 7-7"/>',
 bookmark:'<path d="M6 4h12v17l-6-4-6 4z"/>',
 journal:'<path d="M7 3h13v18H7a3 3 0 0 1-3-3V6a3 3 0 0 1 3-3Z"/><path d="M4 17h16M9 7h7M9 11h5"/>',
 sliders:'<path d="M4 7h6m4 0h6M4 17h10m4 0h2"/><circle cx="12" cy="7" r="2"/><circle cx="16" cy="17" r="2"/>',
 plug:'<path d="M8 3v4m8-4v4M6 7h12v5a6 6 0 0 1-12 0zM12 18v4"/>',
 arrow:'<path d="M4 12h15m-6-6 6 6-6 6"/>',
 plus:'<path d="M12 5v14M5 12h14"/>',
 close:'<path d="m6 6 12 12M6 18 12-12"/>',
 check:'<path d="m5 12 4 4L19 6"/>',
 chevron:'<path d="m9 5 7 7-7 7"/>',
 external:'<path d="M14 3h7v7m-10 3L21 3M10 3H3v18h18v-7"/>',
 shield:'<path d="m12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6z"/><path d="m8 12 3 3 5-6"/>',
 download:'<path d="M12 3v12m-5-5 5 5 5-5M4 17v4h16v-4"/>',
 globe:'<circle cx="12" cy="12" r="9"/><ellipse cx="12" cy="12" rx="4" ry="9"/><path d="M3 12h18"/>',
 more:'<circle cx="5" cy="12" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/>',
 copy:'<rect x="8" y="8" width="12" height="13" rx="2"/><path d="M16 8V3H3v13h5"/>',
 clock:'<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
 calc:'<rect x="5" y="3" width="14" height="18" rx="2"/><path d="M8 7h8M8 11h2m4 0h2M8 15h2m4 0h2"/>',
};
export const icon = (name,cls='') => `<svg aria-hidden="true" class="icon ${cls}" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round">${paths[name] || paths.arrow}</svg>`;
export const badge = (text,type='neutral') => `<span class="badge ${type}">${esc(text)}</span>`;
export const themes = ['Dividendenqualität','KI & Wachstum','Chancen'];
export const options = (items,current) => items.map(x=>`<option ${x===current?'selected':''} value="${esc(x)}">${esc(x)}</option>`).join('');
export const field = (label,input,hint='') => `<label class="field"><span>${label}</span>${input}${hint?`<small>${hint}</small>`:''}</label>`;
export const input = (name,value='',type='text',attrs='') => `<input name="${name}" type="${type}" value="${esc(value)}" ${attrs}>`;
export const sourceLink = (url,label) => /^https:\/\//i.test(url) ? `<a href="${esc(url)}" target="_blank" rel="noreferrer noopener">${esc(label)} ${icon('external')}</a>` : esc(label);
export function modal(title,body,wide=false) {
 document.querySelector('dialog')?.remove();
 const el=document.createElement('dialog'); el.className=wide?'wide':'';
 el.innerHTML=`<div class="dialog-head"><h2>${esc(title)}</h2><button class="icon-button" data-action="close-dialog" aria-label="Schließen">${icon('close')}</button></div><div class="dialog-body">${body}</div>`;
 document.body.append(el);el.showModal();return el;
}
let timer;
export function toast(text,error=false){const el=document.querySelector('#toast');el.textContent=text;el.className=error?'visible error':'visible';clearTimeout(timer);timer=setTimeout(()=>el.className='',6000);}
