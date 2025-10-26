window.AskFeedback = (function(){
  function panelHtml(){
    return '<div class="feedback flex gap-2 mt-3">'
      + '<button class="btn-feedback bg-green-50 hover:bg-green-100 border border-green-300 text-green-700 px-3 py-1 rounded" data-verdict="correct">👍 Correct</button>'
      + '<button class="btn-feedback bg-red-50 hover:bg-red-100 border border-red-300 text-red-700 px-3 py-1 rounded" data-verdict="incorrect">👎 Incorrect</button>'
      + '</div>';
  }
  function sendFeedback(xp_id, verdict, comment){
    return fetch('/api/feedback/submit', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ xp_id, verdict, comment: comment||'' })
    }).then(r=>r.json());
  }
  function attach(container){
    if(!container) return;
    const exists = container.querySelector('.feedback');
    if(exists) return;
    const div = document.createElement('div');
    div.innerHTML = panelHtml();
    container.appendChild(div);
    div.querySelectorAll('.btn-feedback').forEach(btn=>{
      btn.addEventListener('click', async function(){
        const verdict = this.getAttribute('data-verdict');
        const xp_id = window._lastXpId || null;
        const conf = (window._lastResult && window._lastResult.confidence && window._lastResult.confidence.score) ? window._lastResult.confidence.score : undefined;
        if(!xp_id){ if(window.AskUI?.toast) AskUI.toast.error('No experience id yet. Please re-run.'); return; }
        try{
          const res = await sendFeedback(xp_id, verdict, '');
          if(res && res.status==='recorded'){
            if(window.AskUI?.toast){ AskUI.toast.success('Feedback recorded'); }
            container.classList.remove('ring-2','ring-red-300','ring-green-300');
            container.classList.add('ring-2', verdict==='correct'?'ring-green-300':'ring-red-300');
          }else{
            if(window.AskUI?.toast){ AskUI.toast.error('Failed to record feedback'); }
          }
        }catch(e){ if(window.AskUI?.toast){ AskUI.toast.error('Feedback error'); } }
      });
    });
  }
  function bindFeedbackButtons(){
    try{
      // Chat bubble container
      document.querySelectorAll('.results-container').forEach(attach);
      // Secondary panel
      const rc = document.getElementById('results-container'); if(rc) attach(rc);
    }catch(e){}
  }
  return { bindFeedbackButtons, attach };
})();

