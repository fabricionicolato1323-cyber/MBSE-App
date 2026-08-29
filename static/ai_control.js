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

  if (!control || !statusText || !modelText || !actionButton || !modal || !select) {
    return;
  }

  let currentAI = {status: 'off', model: null, message: ''};
  let statusRequestInFlight = false;

  function setMessage(text, kind = '') {
    message.textContent = text || '';
    message.className = `ai-modal-message${kind ? ` ${kind}` : ''}`;
  }

  function renderStatus(ai) {
    currentAI = ai || {status: 'off', model: null, message: ''};
    const status = currentAI.status || 'off';
    control.dataset.status = status;

    if (status === 'active') {
      statusText.textContent = 'AI On';
      modelText.textContent = currentAI.model || '';
      modelText.hidden = !currentAI.model;
      actionButton.textContent = 'AI settings';
      actionButton.disabled = false;
      return;
    }

    modelText.hidden = true;
    modelText.textContent = '';
    if (status === 'activating') {
      statusText.textContent = 'AI activating';
      actionButton.textContent = 'Please wait';
      actionButton.disabled = true;
    } else if (status === 'error') {
      statusText.textContent = 'AI unavailable';
      actionButton.textContent = 'Try again';
      actionButton.disabled = false;
    } else {
      statusText.textContent = 'AI Off';
      actionButton.textContent = 'Activate AI';
      actionButton.disabled = false;
    }
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
      // The main application already reports connection failures. Keep the last
      // known AI status here instead of adding duplicate noise.
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
    disableButton.hidden = currentAI.status !== 'active';
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

      if (currentAI.model && models.includes(currentAI.model)) {
        select.value = currentAI.model;
      }
      select.disabled = false;
      activateButton.disabled = false;
      setMessage(
        currentAI.status === 'active'
          ? 'Choose a model to keep or change the active AI support.'
          : 'Choose the local model to use for AI assistance.'
      );
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
    disableButton.disabled = true;
    setMessage('Disabling AI assistance…');
    try {
      const response = await fetch('/api/ai/disable', {method: 'POST'});
      const data = await response.json().catch(() => ({}));
      if (!response.ok || !data.ok) {
        setMessage(data.error || 'AI assistance could not be disabled.', 'error');
        disableButton.disabled = false;
        return;
      }
      renderStatus({status: 'off', model: null, message: 'AI assistance is off.'});
      closeModal();
      window.setTimeout(refreshStatus, 250);
    } catch (_) {
      setMessage('AI assistance could not be disabled.', 'error');
      disableButton.disabled = false;
    }
  }

  actionButton.addEventListener('click', openModal);
  activateButton.addEventListener('click', activateAI);
  disableButton.addEventListener('click', disableAI);
  cancelButton.addEventListener('click', closeModal);
  backdrop?.addEventListener('click', closeModal);
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && !modal.hidden) closeModal();
  });

  renderStatus(currentAI);
  refreshStatus();
  window.setInterval(refreshStatus, 1000);
})();
