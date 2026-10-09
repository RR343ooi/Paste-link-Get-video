const $=s=>document.querySelector(s);
const resultsEl=$('#results');
const statusEl=$('#status');
const bulkBar=$('#bulkBar');
const bulkQuality=$('#bulkQuality');
const urlInput=$('#urlInput');
const linkCount=$('#linkCount');
const emptyState=$('#emptyState');
let items=[];
// --- Per-user Downloads isolation (client side) ---
// The backend now filters /api/downloads by Flask session cookie, so one
// user never sees another's files. As a second layer, keep this browser's
// own finished downloads in localStorage and render only those.
const MY_FILES_KEY='fmd_my_downloads_v1';
function isHiddenFile(name){
  const b=String(name||'').split('/').pop();
  if(!b) return true;
  if(b==='.gitkeep'||b==='.gitignore'||b==='.DS_Store') return true;
  if(b.startsWith('.')) return true;
  return false;
}
function getMyFiles(){
  try{
    const raw=localStorage.getItem(MY_FILES_KEY);
    const arr=raw?JSON.parse(raw):[];
    return Array.isArray(arr)?arr.filter(f=>f&&f.filename&&!isHiddenFile(f.filename)):[];
  }catch{return [];}
}
function saveMyFile(entry){
  if(!entry||!entry.filename||isHiddenFile(entry.filename)) return;
  const list=getMyFiles().filter(f=>f.filename!==entry.filename);
  list.unshift({filename:entry.filename,size:entry.size||0,ts:Date.now()});
  try{localStorage.setItem(MY_FILES_KEY,JSON.stringify(list.slice(0,100)));}catch{}
}
function renderMyFiles(extraByName){
  const el=$('#fileList');
  const mine=getMyFiles();
  // Merge server sizes (session-filtered) without ever adding foreign names:
  // only filenames already in localStorage OR returned by our own session.
  const merged=mine.map(f=>{
    const extra=extraByName&&extraByName[f.filename];
    return extra!=null?{...f,size:extra}:f;
  });
  if(!merged.length){el.textContent='No files yet.';return;}
  el.innerHTML=merged.map(f=>`<div class="file"><span>${esc(f.filename)} <span class="muted">(${(f.size/1024/1024).toFixed(1)} MB)</span></span><a href="/api/downloads/${encodeURIComponent(f.filename)}">Download</a></div>`).join('');
}
// Clean user-facing error: never show raw cookie/bot-check traces or stack traces.
const YOUTUBE_BLOCKED='This app does not currently support YouTube.';
function friendlyError(msg){
  const m=String(msg||'');
  const low=m.toLowerCase();
  if(low.includes('youtube')||low.includes('youtu.be')||low.includes('cookie')
    ||low.includes('bot check')||low.includes('sign in to confirm')
    ||low.includes("confirm you")){
    return YOUTUBE_BLOCKED;
  }
  return m||'Something went wrong.';
}
function esc(s){return String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
function triggerAutoDownload(fileUrl, fileName) {
  const link = document.createElement('a');
  link.href = fileUrl;
  link.download = fileName || '';
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
}
function parseUrls(text){return text.split(/[\n,]+/).map(s=>s.trim()).filter(Boolean)}
function updateCount(){
  const n=parseUrls(urlInput.value).length;
  linkCount.textContent=n===0?'0 links detected':n===1?'1 link detected':`${n} links detected`;
  linkCount.classList.toggle('has-links',n>0);
  if(n===0) statusEl.textContent='';
}
function fmtDuration(s){
  if(!s&&s!==0) return '';
  const m=Math.floor(s/60),sec=s%60;
  return `${m}:${String(sec).padStart(2,'0')}`;
}
urlInput.addEventListener('input',updateCount);
$('#pasteBtn').onclick=async()=>{
  try{
    const t=await navigator.clipboard.readText();
    if(t){urlInput.value=t;updateCount();urlInput.focus();}
  }catch{urlInput.focus();document.execCommand('paste');}
};
$('#clearBtn').onclick=()=>{
  urlInput.value='';updateCount();resultsEl.innerHTML='';items=[];bulkBar.classList.add('hidden');statusEl.textContent='';emptyState.style.display='';
};
$('#exampleBtn').onclick=()=>{
  urlInput.value='https://x.com/medya3tr/status/2103156250271699248?s=20\nhttps://www.tiktok.com/@qu__y/video/7688788884611681543?is_from_webapp=1&sender_device=pc';
  updateCount();
};
urlInput.addEventListener('keydown',e=>{if((e.ctrlKey||e.metaKey)&&e.key==='Enter') fetchInfo()});
async function fetchInfo(){
  const urls=parseUrls(urlInput.value);
  if(!urls.length){statusEl.textContent='Paste at least one URL.';return;}
  $('#fetchBtn').disabled=true;
  statusEl.textContent='Fetching…';
  resultsEl.innerHTML='';items=[];bulkBar.classList.add('hidden');emptyState.style.display='none';
  bulkQuality.innerHTML='<option value="best">Best</option>';
  try{
    const r=await fetch('/api/analyze',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({urls})});
    const j=await r.json();
    if(!r.ok) throw new Error(friendlyError(j.error)||'Failed');
    const qualities=new Set();
    j.results.forEach(info=>{
      if(info.status==='ok'){info.formats.forEach(f=>{if(f.label) qualities.add(f.height)});items.push(info);}
      else{resultsEl.insertAdjacentHTML('beforeend',`<div class="card" style="padding:16px;border-color:#fecaca"><div class="title">${esc(info.url)}</div><div class="muted">Error: ${esc(friendlyError(info.error))}</div></div>`);}
    });
    qualities.forEach(h=>{if(h) bulkQuality.insertAdjacentHTML('beforeend',`<option value="${h}">${h}p</option>`)});
    items.forEach(renderItem);
    if(items.length) bulkBar.classList.remove('hidden');
    statusEl.textContent=items.length?`Found ${items.length} video(s)`:'No videos found';
    if(!items.length&&!resultsEl.children.length){emptyState.style.display='';statusEl.textContent='No results';}
  }catch(e){statusEl.textContent=friendlyError(e.message);emptyState.style.display='';}
  finally{$('#fetchBtn').disabled=false;}
}
function renderItem(info){
  const opts=info.formats.map(f=>`<option value="${f.height}">${f.label}</option>`).join('');
  const dur=fmtDuration(info.duration);
  const el=document.createElement('div');
  el.className='card item';
  el.innerHTML=`<img class="thumb" src="${info.thumbnail||''}" alt="" onerror="this.style.display='none'"/><div><div class="title">${info.title}</div><div class="meta">${info.uploader||info.extractor||''} ${dur?'· '+dur:''}</div><div class="controls"><label style="font-size:13px;font-weight:600">Quality <select class="q">${opts}</select></label><button class="btn small dlVideo">MP4</button><button class="btn ghost small dlAudio">MP3</button></div><div class="progress hidden"><div class="bar"></div></div><div class="muted out"></div></div>`;
  const qSel=el.querySelector('.q'),bar=el.querySelector('.bar'),prog=el.querySelector('.progress'),out=el.querySelector('.out');
  async function start(mode){
    const quality=qSel.value,endpoint=mode==='audio'?'/api/download/audio':'/api/download/video',body=mode==='audio'?{url:info.url}:{url:info.url,quality};
    out.textContent='Starting…';prog.classList.remove('hidden');bar.style.width='3%';
    try{
      const r=await fetch(endpoint,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
      const j=await r.json();
      if(!r.ok) throw new Error(friendlyError(j.error)||'Download failed');
      poll(j.task_id,bar,prog,out);
    }catch(e){out.textContent=friendlyError(e.message);}
  }
  el.querySelector('.dlVideo').onclick=()=>start('video');
  el.querySelector('.dlAudio').onclick=()=>start('audio');
  resultsEl.appendChild(el);
}
async function poll(id,bar,prog,out,autoDelay=0){
  const t=setInterval(async()=>{
    try{
      const r=await fetch(`/api/download/status/${id}`);
      const j=await r.json();
      if(!r.ok) throw new Error(friendlyError(j.error));
      bar.style.width=(j.progress||0)+'%';
      if(j.status==='completed'){clearInterval(t);const downloadUrl=`/api/downloads/${encodeURIComponent(j.filename)}`;out.innerHTML=`Done — <a href="${downloadUrl}">Download ${esc(j.filename)}</a>`;prog.classList.add('hidden');if(j.filename&&!isHiddenFile(j.filename)){saveMyFile({filename:j.filename});loadFiles();setTimeout(()=>triggerAutoDownload(downloadUrl,j.filename),autoDelay);}}
      else if(j.status==='error'){clearInterval(t);out.textContent='Error: '+friendlyError(j.error||'unknown');}
      else{out.textContent=j.status+' '+(j.progress||0)+'%';}
    }catch(e){clearInterval(t);out.textContent=friendlyError(e.message);}
  },900);
}
async function downloadAll(mode){
  const urls=items.map(i=>i.url);
  if(!urls.length) return;
  const quality=bulkQuality.value;
  statusEl.textContent='Starting batch…';
  const r=await fetch('/api/download/all',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({urls,quality,mode})});
  const j=await r.json();
  if(!r.ok){statusEl.textContent=friendlyError(j.error);return;}
  statusEl.textContent=`Queued ${j.tasks.length} download(s) — check each card`;
  const cards=[...resultsEl.querySelectorAll('.item')];
  j.tasks.forEach((t,i)=>{
    const card=cards[i];if(!card) return;
    const bar=card.querySelector('.bar'),prog=card.querySelector('.progress'),out=card.querySelector('.out');
    prog.classList.remove('hidden');poll(t.task_id,bar,prog,out,i*400);
  });
}
async function loadFiles(){
  // Render this browser's own list instantly, then reconcile sizes with the
  // session-filtered /api/downloads response (which only contains our files).
  renderMyFiles();
  try{
    const r=await fetch('/api/downloads');const j=await r.json();
    if(!r.ok) return;
    const byName={};
    (j.files||[]).forEach(f=>{if(f&&f.filename&&!isHiddenFile(f.filename)) byName[f.filename]=f.size||0;});
    // Adopt server-known files into localStorage (e.g. after storage was cleared
    // but the session cookie is still valid) — server list is already per-session.
    Object.keys(byName).forEach(name=>{
      if(!getMyFiles().some(f=>f.filename===name)) saveMyFile({filename:name,size:byName[name]});
    });
    renderMyFiles(byName);
  }catch{}
}
$('#fetchBtn').onclick=fetchInfo;
$('#dlAllVideo').onclick=()=>downloadAll('video');
$('#dlAllAudio').onclick=()=>downloadAll('audio');
updateCount();loadFiles();
