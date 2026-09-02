(() => {
  const control = document.getElementById('aiControl');
  const statusText = document.getElementById('aiStatusText');
  const modelText = document.getElementById('aiModelText');
  const actionButton = document.getElementById('aiActionButton');
  const modal = document.getElementById('aiModal');
  const select = document.getElementById('aiModelSelect');
  const message = document.getElementById('aiModalMessage');
  const activateButton = document.getElementById('activateAIButton');
  const disableButton = document.getElementById('disableAIButton');
  const cancelButton = document.getElementById('cancelAIButton');
  const backdrop = modal?.querySelector('[data-close-ai]');

  if (!control || !statusText || !actionButton || !modal || !select) {
    return;
  }

  let currentAI = {status: 'off', model: null, message: ''};
  let statusRequestInFlight = false;

  function setMessage(text, kind = '') {
    if (!message) return;
    message.textContent = text || '';
    message.className = `ai-modal-message${kind ? ` ${kind}` : ''}`;
  }

  function renderStatus(ai) {
    currentAI = ai || {status: 'off', model: null, message: ''};
    const status = currentAI.status || 'off';
    control.dataset.status = status;

    // The selected model remains session state, not top-bar UI content.
    if (modelText) {
      modelText.hidden = true;
      modelText.textContent = '';
    }

    if (status === 'active') {
      statusText.textContent = 'AI On';
      actionButton.textContent = 'Deactivate AI';
      actionButton.disabled = false;
      return;
    }

    if (status === 'activating') {
      statusText.textContent = 'AI activating';
      actionButton.textContent = 'Please wait';
      actionButton.disabled = true;
      return;
    }

    // Errors are presented as an off state in the compact control. Details
    // appear only in the activation dialog if the user tries again.
    statusText.textContent = 'AI Off';
    actionButton.textContent = 'Activate AI';
    actionButton.disabled = false;
  }

  async function refreshStatus() {
    if (statusRequestInFlight) return;
    statusRequestInFlight = true;
    try {
      const response = await fetch('/api/state', {cache: 'no-store'});
      if (!response.ok) return;
      const state = await response.json();
      renderStatus(state.ai || {status: 'off'});
    } catch (_) {
      // The main application reports connection failures. Preserve the last
      // known state here instead of adding duplicate UI noise.
    } finally {
      statusRequestInFlight = false;
    }
  }

  function openModal() {
    modal.hidden = false;
    setMessage('Checking locally installed models…');
    select.innerHTML = '';
    select.disabled = true;
    activateButton.disabled = true;
    if (disableButton) disableButton.hidden = true;
    loadModels();
  }

  function closeModal() {
    modal.hidden = true;
    actionButton.focus();
  }

  async function loadModels() {
    try {
      const response = await fetch('/api/ai/models', {cache: 'no-store'});
      const data = await response.json().catch(() => ({}));
      if (!response.ok || !data.ok) {
        setMessage(data.error || 'The local AI service is unavailable.', 'error');
        return;
      }

      const models = Array.isArray(data.models) ? data.models : [];
      select.innerHTML = '';
      models.forEach(model => {
        const option = document.createElement('option');
        option.value = model;
        option.textContent = model;
        select.appendChild(option);
      });

      if (!models.length) {
        setMessage('No local AI models are installed.', 'error');
        return;
      }

      select.disabled = false;
      activateButton.disabled = false;
      setMessage('Choose the local model to use for AI assistance.');
      select.focus();
    } catch (_) {
      setMessage('The local AI service is unavailable.', 'error');
    }
  }

  async function activateAI() {
    const model = select.value;
    if (!model) return;
    activateButton.disabled = true;
    select.disabled = true;
    setMessage('Activating AI assistance…');

    try {
      const response = await fetch('/api/ai/activate', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({model})
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok || !data.ok) {
        setMessage(data.error || 'AI assistance could not be activated.', 'error');
        select.disabled = false;
        activateButton.disabled = false;
        return;
      }
      renderStatus({status: 'activating', model, message: 'Activating AI assistance…'});
      closeModal();
      window.setTimeout(refreshStatus, 250);
    } catch (_) {
      setMessage('AI assistance could not be activated.', 'error');
      select.disabled = false;
      activateButton.disabled = false;
    }
  }

  async function disableAI() {
    actionButton.disabled = true;
    control.dataset.status = 'activating';
    statusText.textContent = 'AI deactivating';
    actionButton.textContent = 'Please wait';
    try {
      const response = await fetch('/api/ai/disable', {method: 'POST'});
      const data = await response.json().catch(() => ({}));
      if (!response.ok || !data.ok) {
        renderStatus(currentAI);
        return;
      }
      renderStatus({status: 'off', model: null, message: 'AI assistance is off.'});
      if (!modal.hidden) closeModal();
      window.setTimeout(refreshStatus, 250);
    } catch (_) {
      renderStatus(currentAI);
    }
  }

  actionButton.addEventListener('click', () => {
    if (currentAI.status === 'active') {
      disableAI();
    } else {
      openModal();
    }
  });
  activateButton.addEventListener('click', activateAI);
  cancelButton?.addEventListener('click', closeModal);
  backdrop?.addEventListener('click', closeModal);
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && !modal.hidden) closeModal();
  });

  renderStatus(currentAI);
  refreshStatus();
  window.setInterval(refreshStatus, 1000);
})();
