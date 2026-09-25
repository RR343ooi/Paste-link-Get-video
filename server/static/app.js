const $=s=>document.querySelector(s);
const resultsEl=$('#results');
const statusEl=$('#status');
const bulkBar=$('#bulkBar');
const bulkQuality=$('#bulkQuality');
const urlInput=$('#urlInput');
const linkCount=$('#linkCount');
const emptyState=$('#emptyState');
let items=[];
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
    if(!r.ok) throw new Error(j.error||'Failed');
    const qualities=new Set();
    j.results.forEach(info=>{
      if(info.status==='ok'){info.formats.forEach(f=>{if(f.label) qualities.add(f.height)});items.push(info);}
      else{resultsEl.insertAdjacentHTML('beforeend',`<div class="card" style="padding:16px;border-color:#fecaca"><div class="title">${info.url}</div><div class="muted">Error: ${info.error}</div></div>`);}
    });
    qualities.forEach(h=>{if(h) bulkQuality.insertAdjacentHTML('beforeend',`<option value="${h}">${h}p</option>`)});
    items.forEach(renderItem);
    if(items.length) bulkBar.classList.remove('hidden');
    statusEl.textContent=items.length?`Found ${items.length} video(s)`:'No videos found';
    if(!items.length&&!resultsEl.children.length){emptyState.style.display='';statusEl.textContent='No results';}
  }catch(e){statusEl.textContent=e.message;emptyState.style.display='';}
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
      if(!r.ok) throw new Error(j.error||'Download failed');
      poll(j.task_id,bar,prog,out);
    }catch(e){out.textContent=e.message;}
  }
  el.querySelector('.dlVideo').onclick=()=>start('video');
  el.querySelector('.dlAudio').onclick=()=>start('audio');
  resultsEl.appendChild(el);
}
async function poll(id,bar,prog,out){
  const t=setInterval(async()=>{
    try{
      const r=await fetch(`/api/download/status/${id}`);
      const j=await r.json();
      if(!r.ok) throw new Error(j.error);
      bar.style.width=(j.progress||0)+'%';
      if(j.status==='completed'){clearInterval(t);out.innerHTML=`Done — <a href="/api/downloads/${encodeURIComponent(j.filename)}">Download ${j.filename}</a>`;prog.classList.add('hidden');loadFiles();}
      else if(j.status==='error'){clearInterval(t);out.textContent='Error: '+(j.error||'unknown');}
      else{out.textContent=j.status+' '+(j.progress||0)+'%';}
    }catch(e){clearInterval(t);out.textContent=e.message;}
  },900);
}
async function downloadAll(mode){
  const urls=items.map(i=>i.url);
  if(!urls.length) return;
  const quality=bulkQuality.value;
  statusEl.textContent='Starting batch…';
  const r=await fetch('/api/download/all',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({urls,quality,mode})});
  const j=await r.json();
  if(!r.ok){statusEl.textContent=j.error;return;}
  statusEl.textContent=`Queued ${j.tasks.length} download(s) — check each card`;
  const cards=[...resultsEl.querySelectorAll('.item')];
  j.tasks.forEach((t,i)=>{
    const card=cards[i];if(!card) return;
    const bar=card.querySelector('.bar'),prog=card.querySelector('.progress'),out=card.querySelector('.out');
    prog.classList.remove('hidden');poll(t.task_id,bar,prog,out);
  });
}
async function loadFiles(){
  try{
    const r=await fetch('/api/downloads');const j=await r.json();
    const el=$('#fileList');
    if(!j.files.length){el.textContent='No files yet.';return;}
    el.innerHTML=j.files.map(f=>`<div class="file"><span>${f.filename} <span class="muted">(${(f.size/1024/1024).toFixed(1)} MB)</span></span><a href="/api/downloads/${encodeURIComponent(f.filename)}">Download</a></div>`).join('');
  }catch{}
}
$('#fetchBtn').onclick=fetchInfo;
$('#dlAllVideo').onclick=()=>downloadAll('video');
$('#dlAllAudio').onclick=()=>downloadAll('audio');
updateCount();loadFiles();
