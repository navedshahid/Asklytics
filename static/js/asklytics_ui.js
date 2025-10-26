/* asklytics_ui.js - lightweight UI helpers for AskLytics */
(function(){
  const LS_MODE_KEY = 'asklytics_ui_mode';
  function _toastRender(type, msg){
    const el = document.createElement('div');
    el.className = `toast ${type}`;
    el.textContent = msg;
    document.body.appendChild(el);
    setTimeout(()=>{ el.remove(); }, 2800);
  }
  // Provide AskUI.toast.info/error/success API expected by callers
  const toast = {
    info: (msg)=>_toastRender('info', msg),
    error: (msg)=>_toastRender('error', msg),
    success: (msg)=>_toastRender('success', msg)
  };
  function setMode(mode){
    const m = mode === 'dev' ? 'dev' : 'biz';
    localStorage.setItem(LS_MODE_KEY, m);
    document.body.classList.toggle('biz', m==='biz');
    document.body.classList.toggle('dev', m==='dev');
    const panel = document.getElementById('insight-panel');
    if(panel){ panel.classList.toggle('hidden', m!=='biz'); }
  }
  function getMode(){ return localStorage.getItem(LS_MODE_KEY) || 'biz'; }
  function loadingStart(target){ if(!target) return; target.setAttribute('aria-busy','true'); }
  function loadingStop(target){ if(!target) return; target.removeAttribute('aria-busy'); }
  function toCSV(columns, rows){
    const header = columns.join(',');
    const body = rows.map(r=> columns.map(c=> JSON.stringify(r[c] ?? '')).join(',')).join('\n');
    return header + '\n' + body;
  }
  function renderSummaryCard(data){
    const panel = document.getElementById('insight-panel'); if(!panel) return;
    panel.classList.remove('hidden');
    const sum = panel.querySelector('.insight-summary');
    const badge = document.getElementById('confidence-badge');
    const prov = panel.querySelector('.provenance');
    // Compose summary + optional bullets
    if(sum){
      const bullets = (data.bullets||[]).slice(0,3).map(b=> `• ${b}`).join('  ');
      sum.textContent = [data.summary||'', bullets].filter(Boolean).join('  ');
    }
    if(prov) prov.textContent = data.provenance || '';
    if(badge){
      badge.textContent = `Confidence: ${data.confidence?.label || '—'}`;
      badge.className = 'badge ' + (data.confidence?.label ? 'confidence-' + (data.confidence.label||'').toLowerCase() : '');
    }
  }
  function renderChart(columns, rows){
    const canvas = document.getElementById('resultChart'); if(!canvas) return;
    if(window.currentChart){ try{ window.currentChart.destroy(); }catch(e){} }
    if(!columns || !rows || !rows.length){ canvas.classList.add('hidden'); return; }
    const ctx = canvas.getContext('2d');
    const first = columns[0];
    const numericCols = columns.filter(c=> rows.some(r=> typeof r[c]==='number'));
    if(numericCols.length===0){ canvas.classList.add('hidden'); return; }
    const cat = first;
    const measure = numericCols.includes(first) && numericCols[1] ? numericCols[1] : numericCols[0];
    const labels = rows.map(r=> r[cat]);
    const data = rows.map(r=> r[measure]);
    canvas.classList.remove('hidden');
    /* global Chart */
    window.currentChart = new Chart(ctx, {
      type: (new Date(labels[0]).toString() !== 'Invalid Date' && !isNaN(Date.parse(labels[0]))) ? 'line' : 'bar',
      data: { labels, datasets: [{ label: measure, data, borderColor:'#2563eb', backgroundColor:'#93c5fd' }]},
      options: { responsive:true, scales:{ y:{ beginAtZero:true }}}
    });
  }
  async function withRetry(fn, attempts=2){
    let last; for(let i=0;i<attempts;i++){ try{ return await fn(); }catch(e){ last=e; } }
    throw last;
  }
  window.AskUI = { toast, setMode, getMode, loadingStart, loadingStop, toCSV, renderSummaryCard, renderChart, withRetry };
})();

// Tab handling and button wiring for AskLytics main page
(function(){
  function qs(id){ return document.getElementById(id); }
  function activateTab(key){
    const panes = ['results','visuals','sql'];
    panes.forEach(p=>{ const el=qs('tab-'+p); if(el){ el.classList.toggle('hidden', p!==key); el.classList.toggle('active', p===key); } });
    localStorage.setItem('ask_tab', key);
  }
  window.AskTabs = { activate: activateTab };

  document.addEventListener('click', async (e)=>{
    const b = e.target.closest('button'); if(!b) return;
    const tab = b.getAttribute('data-tab'); if(tab){ e.preventDefault(); activateTab(tab); return; }
    if(b.id==='btn-download-csv'){
      const res = window._lastResult; if(!res) return;
      const csv = AskUI.toCSV(res.columns||[], res.rows||[]);
      const blob = new Blob([csv], {type:'text/csv'}); const a=document.createElement('a'); a.href=URL.createObjectURL(blob); a.download='result.csv'; a.click();
    }
    if(b.id==='btn-explain-quick'){
      const res = window._lastResult; if(!res) return; b.disabled=true;
      try{
        const ex = await fetch('/api/insight/summarize',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({columns:res.columns,rows:res.rows,query:res.query})}).then(r=>r.json());
        AskUI.renderSummaryCard({ summary: ex.summary, bullets: ex.bullets, provenance: qs('insight-panel')?.querySelector('.provenance')?.textContent, confidence: window._lastResult?.confidence });
      }catch(err){ AskUI.toast.error('Explain failed'); } finally{ b.disabled=false; }
    }
    if(b.id==='btn-why'){
      const res = window._lastResult; if(!res) return; b.disabled=true;
      try{
        const p = await fetch('/api/insight/provenance',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({sql:res.sql,validator_signals:{}})}).then(r=>r.json());
        AskUI.renderSummaryCard({ summary: qs('insight-panel')?.querySelector('.insight-summary')?.textContent, bullets: [], provenance: p.provenance, confidence: window._lastResult?.confidence });
      }catch(err){ AskUI.toast.error('Why this failed'); } finally{ b.disabled=false; }
    }
  });

  // New chat behavior: destroy chart, clear panes
  window.addEventListener('DOMContentLoaded', ()=>{
    const newBtn = qs('new-conversation-btn');
    if(newBtn){ newBtn.addEventListener('click', async ()=>{
      // Clear UI first
      if(window.currentChart){ try{ window.currentChart.destroy(); }catch(e){} window.currentChart=null; }
      const resC = qs('results-container'); if(resC) resC.innerHTML='';
      const sqlT = qs('sqlText'); if(sqlT) sqlT.textContent='';
      const panel = qs('insight-panel'); if(panel) panel.classList.add('hidden');
      const card = qs('result-tabs'); if(card) card.classList.add('hidden');
      activateTab('results');
      // Attempt to create a new server thread if helpers exist
      try{
        if(typeof apiCreateThread === 'function' && typeof loadThread === 'function' && typeof renderThreadsList === 'function'){
          const t = await apiCreateThread('New Chat');
          if(t && t.id){ await loadThread(t.id); }
        }
      }catch(err){ AskUI.toast.info('Chat session limit reached or unavailable.'); }
    }); }
    // restore tab state
    const t = localStorage.getItem('ask_tab') || 'results'; activateTab(t);
  });
})();
