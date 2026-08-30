(() => {
  const saveButton = document.getElementById('saveModelButton');
  const loadButton = document.getElementById('loadModelButton');
  const loadInput = document.getElementById('loadModelInput');
  const saveModal = document.getElementById('saveModelModal');
  const saveNameInput = document.getElementById('modelNameInput');
  const saveMessage = document.getElementById('saveModelMessage');
  const cancelSaveButton = document.getElementById('cancelSaveModelButton');
  const confirmSaveButton = document.getElementById('confirmSaveModelButton');
  const modelFileName = document.getElementById('modelFileName');
  if (!saveButton || !loadButton || !loadInput || !saveModal || !saveNameInput) return;

  let currentModelName = '';
  let pendingSaveContinuation = null;
  const baseSendValueForModelFiles = sendValue;
  const baseApplyStateForModelFiles = applyState;
  const baseClearRenderedSessionForModelFiles = clearRenderedSession;

  function setCurrentModelName(name) {
    currentModelName = String(name || '').trim();
    if (!modelFileName) return;
    modelFileName.textContent = currentModelName;
    modelFileName.hidden = !currentModelName;
    modelFileName.title = currentModelName;
  }

  function suggestedFilename(name) {
    const safe = String(name || 'Operational Analysis model')
      .replace(/[<>:"/\\|?*\u0000-\u001f]/g, '_')
      .replace(/\s+/g, ' ')
      .trim();
    return `${safe || 'Operational Analysis model'}.json`;
  }

  function showSaveMessage(message, {error = false} = {}) {
    if (!saveMessage) return;
    saveMessage.textContent = message || '';
    saveMessage.classList.toggle('error', error);
  }

  function openSaveModal(continuation = null) {
    pendingSaveContinuation = continuation;
    showSaveMessage('');
    saveNameInput.value = currentModelName || 'Operational Analysis model';
    saveModal.hidden = false;
    requestAnimationFrame(() => {
      saveNameInput.focus();
      saveNameInput.select();
    });
  }

  function closeSaveModal() {
    saveModal.hidden = true;
    pendingSaveContinuation = null;
    saveButton.focus();
  }

  async function requestModelExport(modelName) {
    const response = await fetch('/api/model/export', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({model_name: modelName})
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok || !data.model) {
      throw new Error(data.error || 'The model could not be prepared for saving.');
    }
    return data;
  }

  async function writeModelToChosenLocation(model, modelName) {
    const text = JSON.stringify(model, null, 2);
    const filename = suggestedFilename(modelName);

    if (typeof window.showSaveFilePicker === 'function') {
      const handle = await window.showSaveFilePicker({
        suggestedName: filename,
        types: [{
          description: 'Operational Analysis model',
          accept: {'application/json': ['.json']}
        }]
      });
      const writable = await handle.createWritable();
      await writable.write(text);
      await writable.close();
      return;
    }

    const blob = new Blob([text], {type: 'application/json'});
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = filename;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);
  }

  async function saveCurrentModel() {
    const name = saveNameInput.value.trim();
    if (!name) {
      showSaveMessage('Enter a model name.', {error: true});
      return;
    }

    confirmSaveButton.disabled = true;
    showSaveMessage('Preparing model…');
    try {
      const result = await requestModelExport(name);
      await writeModelToChosenLocation(result.model, result.model_name || name);
      const continuation = pendingSaveContinuation;
      setCurrentModelName(result.model_name || name);
      saveModal.hidden = true;
      pendingSaveContinuation = null;
      statusLine.textContent = `Saved: ${result.model_name || name}`;
      if (continuation) {
        await baseSendValueForModelFiles(continuation.value, continuation.displayValue);
      }
    } catch (error) {
      if (error?.name === 'AbortError') {
        showSaveMessage('Save cancelled. Choose a location when you are ready.');
      } else {
        showSaveMessage(error?.message || 'The model could not be saved.', {error: true});
      }
    } finally {
      confirmSaveButton.disabled = false;
    }
  }

  function resetRevisionClientState() {
    if (typeof revisionLastTurnsSignature !== 'undefined') revisionLastTurnsSignature = '';
    if (typeof revisionLastInteractionSignature !== 'undefined') revisionLastInteractionSignature = '';
    if (typeof revisionRequestInFlight !== 'undefined') revisionRequestInFlight = false;
    if (typeof revisionRequestSourceAssistantId !== 'undefined') revisionRequestSourceAssistantId = null;
    if (typeof revisionCurrentAssistantId !== 'undefined') revisionCurrentAssistantId = null;
  }

  async function loadSelectedModel(file) {
    let model;
    try {
      model = JSON.parse(await file.text());
    } catch (error) {
      setBusy(false, 'The selected file is not valid JSON.');
      return;
    }

    setBusy(true, 'Loading model…');
    if (stateRequest) {
      stateRequest.controller.abort();
      stateRequest = null;
    }

    try {
      const response = await fetch('/api/model/load', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({model, file_name: file.name})
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok || !data.session_id) {
        setBusy(false, data.error || 'The selected model could not be loaded.');
        return;
      }

      activeSessionId = data.session_id;
      resetRevisionClientState();
      baseClearRenderedSessionForModelFiles();
      setCurrentModelName(data.model_name || file.name.replace(/\.json$/i, ''));
      await pollState({force: true});
    } catch (error) {
      setBusy(false, 'Connection to the local app was interrupted while loading the model.');
    }
  }

  sendValue = async function modelFileAwareSendValue(value, displayValue = null) {
    const label = String(displayValue || '').trim().toLocaleLowerCase();
    if (label === 'save' || label === 'save model') {
      openSaveModal({value, displayValue});
      return;
    }
    return baseSendValueForModelFiles(value, displayValue);
  };

  applyState = function modelFileApplyState(state) {
    baseApplyStateForModelFiles(state);
    const stateName = String(state?.model?.name || '').trim();
    if (stateName) setCurrentModelName(stateName);
  };

  clearRenderedSession = function modelFileClearRenderedSession() {
    baseClearRenderedSessionForModelFiles();
    setCurrentModelName('');
  };

  saveButton.addEventListener('click', () => openSaveModal());
  loadButton.addEventListener('click', () => loadInput.click());
  loadInput.addEventListener('change', () => {
    const file = loadInput.files?.[0];
    loadInput.value = '';
    if (file) loadSelectedModel(file);
  });
  cancelSaveButton?.addEventListener('click', closeSaveModal);
  confirmSaveButton?.addEventListener('click', saveCurrentModel);
  saveModal.querySelector('[data-close-save-model]')?.addEventListener('click', closeSaveModal);
  saveNameInput.addEventListener('keydown', event => {
    if (event.key === 'Enter') {
      event.preventDefault();
      saveCurrentModel();
    }
  });

  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && !saveModal.hidden) closeSaveModal();
  });
})();

// Normalize projected edge identities before the Operational Scenario module is
// evaluated. This prevents unrelated NetworkX edges that share key=0 (or any
// other per-pair key) from sharing one diagram selection identity.
import('./oa_scenario_projection_fix.js')
  .catch(error => {
    console.error('Operational Scenario projection fixes could not be loaded.', error);
  })
  .then(() => import('./oa_scenario.js'))
  .then(() => import('./oa_scenario_ui_fixes.js'))
  .then(() => import('./oa_interaction_anchor_drag.js'))
  .then(() => import('./oa_interaction_overlap_routing.js'))
  .then(() => import('./oa_scenario_pseudocode_compact.js'))
  .catch(error => {
    console.error('Operational Scenario UI could not be loaded.', error);
  });
