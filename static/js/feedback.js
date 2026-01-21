window.AskFeedback = (function(){
  const state = {
    xpId: null,
    pending: null,
    status: 'waiting_xp',
    lastError: '',
    containers: new Set()
  };

  function panelHtml(){
    return [
      '<div class="feedback flex items-center gap-3 mt-3">',
        '<div class="feedback-actions flex gap-2">',
          '<button type="button" class="btn-feedback bg-green-50 hover:bg-green-100 border border-green-300 text-green-700 px-3 py-1 rounded" data-verdict="correct" disabled>&#128077; Correct</button>',
          '<button type="button" class="btn-feedback bg-red-50 hover:bg-red-100 border border-red-300 text-red-700 px-3 py-1 rounded" data-verdict="incorrect" disabled>&#128078; Incorrect</button>',
        '</div>',
        '<span class="feedback-status text-sm text-gray-500"></span>',
      '</div>'
    ].join('');
  }

  async function sendFeedback(xpId, verdict, comment){
    const res = await fetch('/api/feedback', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ xp_id: xpId, verdict, comment: comment || '' })
    });
    if(!res.ok){
      const payload = await res.json().catch(()=>({}));
      throw new Error(payload?.error || res.statusText || 'Feedback failed');
    }
    return res.json();
  }

  function setStatus(status, errorMessage){
    state.status = status;
    if(errorMessage){ state.lastError = errorMessage; }
    state.containers.forEach(ctx => applyStateToContainer(ctx));
  }

  function applyStateToContainer(ctx){
    if(!ctx) return;
    const { wrapper, container } = ctx;
    const buttons = wrapper.querySelectorAll('.btn-feedback');
    const statusEl = wrapper.querySelector('.feedback-status');

    const disableButtons = (value) => { buttons.forEach(btn => { btn.disabled = value; }); };
    const resetStatus = () => {
      statusEl.textContent = '';
      statusEl.classList.add('hidden');
      statusEl.classList.remove('text-green-600','text-red-600','text-gray-500');
    };
    const showStatus = (text, klass) => {
      statusEl.textContent = text;
      statusEl.classList.remove('hidden','text-green-600','text-red-600','text-gray-500');
      statusEl.classList.add(klass || 'text-gray-500');
    };

    switch(state.status){
      case 'waiting_xp':
        disableButtons(true);
        showStatus('Saving experience…', 'text-gray-500');
        break;
      case 'idle':
        disableButtons(false);
        resetStatus();
        break;
      case 'submitting':
        disableButtons(true);
        showStatus('Submitting feedback…', 'text-gray-500');
        break;
      case 'submitted':
        disableButtons(true);
        showStatus('Thanks! Feedback recorded.', 'text-green-600');
        break;
      case 'error':
        disableButtons(false);
        showStatus(state.lastError || 'Feedback failed. Try again.', 'text-red-600');
        break;
      case 'disabled':
      default:
        disableButtons(true);
        showStatus('Feedback unavailable for this query.', 'text-gray-500');
        break;
    }

    if(state.status === 'submitted' && ctx.lastVerdict){
      container.classList.remove('ring-2','ring-red-300','ring-green-300');
      container.classList.add('ring-2', ctx.lastVerdict === 'correct' ? 'ring-green-300' : 'ring-red-300');
    }else{
      container.classList.remove('ring-2','ring-red-300','ring-green-300');
    }
  }

  function handleVerdict(verdict, ctx){
    if(state.status === 'submitted' || state.status === 'submitting') return;

    if(!state.xpId){
      state.pending = { verdict, ctx };
      setStatus('waiting_xp');
      if(window.AskUI?.toast){ AskUI.toast.info('Logging experience… feedback will send once ready.'); }
      return;
    }

    submitVerdict(verdict, ctx);
  }

  async function submitVerdict(verdict, ctx){
    try {
      setStatus('submitting');
      const result = await sendFeedback(state.xpId, verdict, '');
      if(result && result.status === 'recorded'){
        ctx.lastVerdict = verdict;
        setStatus('submitted');
        if(window.AskUI?.toast){ AskUI.toast.success('Feedback recorded'); }
        if(window.markFeedbackSubmitted){ try { await window.markFeedbackSubmitted(verdict); } catch(e){} }
      }else{
        ctx.lastVerdict = null;
        setStatus('error', 'Failed to record feedback.');
        if(window.AskUI?.toast){ AskUI.toast.error('Failed to record feedback'); }
      }
    } catch (err) {
      ctx.lastVerdict = null;
      setStatus('error', err?.message || 'Feedback error');
      if(window.AskUI?.toast){ AskUI.toast.error(err?.message || 'Feedback error'); }
    }
  }

  function attach(container){
    if(!container) return;
    const exists = container.querySelector('.feedback');
    if(exists){
      state.containers.forEach(ctx => { if(ctx && ctx.wrapper === exists){ applyStateToContainer(ctx); } });
      return;
    }

    const div = document.createElement('div');
    div.innerHTML = panelHtml();
    container.appendChild(div);

    const wrapper = div.querySelector('.feedback');
    const ctx = { wrapper, container, lastVerdict: null };
    state.containers.add(ctx);

    wrapper.querySelectorAll('.btn-feedback').forEach(btn => {
      btn.addEventListener('click', () => handleVerdict(btn.getAttribute('data-verdict'), ctx));
    });

    applyStateToContainer(ctx);
  }

  function prepareForNewResult(){
    state.xpId = null;
    state.pending = null;
    state.status = 'waiting_xp';
    state.lastError = '';
    state.containers = new Set();
  }

  function onExperienceSaved(xpId){
    if(!xpId) return;
    const parsed = parseInt(xpId, 10);
    if(Number.isNaN(parsed)) return;
    state.xpId = parsed;
    if(state.status !== 'submitted'){ setStatus('idle'); }
    if(state.pending){
      const { verdict, ctx } = state.pending;
      state.pending = null;
      submitVerdict(verdict, ctx);
    }
  }

  function onStreamFinished(silent = false){
    if(state.status === 'waiting_xp' && !state.xpId){
      state.pending = null;
      setStatus('disabled');
      if(!silent && window.AskUI?.toast){ AskUI.toast.error('Result was not logged, so feedback is unavailable. Please rerun.'); }
    }
  }

  function bindFeedbackButtons(){
    try {
      const slot = document.getElementById('feedback-panel-slot'); if(slot) attach(slot);
    } catch (e) {/* ignore */}
  }

  function restoreSubmitted(verdict){
    state.status = 'submitted';
    state.containers.forEach(ctx => { ctx.lastVerdict = verdict || 'correct'; applyStateToContainer(ctx); });
  }

  return {
    bindFeedbackButtons,
    attach,
    prepareForNewResult,
    onExperienceSaved,
    onStreamFinished,
    restoreSubmitted
  };
})();
