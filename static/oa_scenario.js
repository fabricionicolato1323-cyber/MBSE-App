import './oa_diagram_v4_interaction.js';
import './oa_diagram_port_drag.js';
import {state, edgeId, selectionKey} from './oa_diagram_v2_state.js';
import {el, updateSelection} from './oa_diagram_v2_render.js';

const authoring = {
  active: false,
  name: '',
  steps: [],
  currentActivityId: null,
  submitting: false,
};

let latestModel = {nodes: [], drafts: [], edges: [], scenarios: []};
let latestSession = '';
let latestWaiting = false;
let activeScenarioId = null;
let edgeObserver = null;

function ensureStyles() {
  const files = [
    'oa_diagram_capella.css',
    'oa_diagram_v4.css',
    'oa_diagram_port_drag.css',
    'oa_scenario.css',
  ];
  files.forEach(file => {
    const href = new URL(`./${file}`, import.meta.url).href;
    if (document.querySelector(`link[data-oa-style="${file}"]`)) return;
    const link = document.createElement('link');
    link.rel = 'stylesheet';
    link.href = href;
    link.dataset.oaStyle = file;
    document.head.appendChild(link);
  });
}

const clean = value => String(value ?? '').replace(/\s+/g, ' ').trim();

function scenarioList(model = latestModel) {
  return Array.isArray(model?.scenarios) ? model.scenarios : [];
}

function modelNodes() {
  return Array.isArray(latestModel?.nodes) ? latestModel.nodes : [];
}

function modelEdges() {
  return Array.isArray(latestModel?.edges) ? latestModel.edges : [];
}

function nodeById(id) {
  return modelNodes().find(node => node.id === id) || null;
}

function edgeRecords(type = null) {
  return modelEdges()
    .map((edge, index) => ({edge, index, diagramId: edgeId(edge, index)}))
    .filter(item => !type || item.edge.type === type);
}

function exchangeByDiagramId(diagramId) {
  return edgeRecords('OPERATIONAL_EXCHANGE')
    .find(item => item.diagramId === diagramId) || null;
}

function performersForActivity(activityId) {
  return modelEdges()
    .filter(edge => edge.type === 'PERFORMS' && edge.target === activityId)
    .map(edge => edge.source);
}

function communicationMatches(edge, sourceParticipant, targetParticipant) {
  return (
    (edge.source === sourceParticipant && edge.target === targetParticipant) ||
    (edge.source === targetParticipant && edge.target === sourceParticipant)
  );
}

function communicationRefMatches(ref, exchange) {
  if (!ref || typeof ref !== 'object') return false;
  if (ref.source_activity_id !== exchange.source) return false;
  if (ref.target_activity_id !== exchange.target) return false;
  const refName = clean(ref.exchange_name);
  return !refName || refName === clean(exchange.name);
}

function communicationForExchange(exchange) {
  const candidates = [];
  const communications = edgeRecords('COMMUNICATION_MEAN');

  performersForActivity(exchange.source).forEach(sourceParticipant => {
    performersForActivity(exchange.target).forEach(targetParticipant => {
      if (sourceParticipant === targetParticipant) return;
      communications.forEach(item => {
        if (communicationMatches(item.edge, sourceParticipant, targetParticipant)) {
          candidates.push({...item, sourceParticipant, targetParticipant});
        }
      });
    });
  });

  const explicit = candidates.filter(item =>
    Array.isArray(item.edge.exchange_refs) &&
    item.edge.exchange_refs.some(ref => communicationRefMatches(ref, exchange))
  );
  if (explicit.length === 1) return explicit[0];
  if (explicit.length > 1) return null;
  if (clean(exchange.communication_assignment).toLowerCase() === 'none') return null;

  const byMedium = new Map();
  candidates.forEach(item => byMedium.set(item.diagramId, item));
  return byMedium.size === 1 ? [...byMedium.values()][0] : null;
}

function activityStep(activityId) {
  return {
    kind: 'activity',
    activity_id: activityId,
  };
}

function interactionStep(record) {
  const exchange = record.edge;
  const item = {
    kind: 'interaction',
    source_activity_id: exchange.source,
    target_activity_id: exchange.target,
    edge_key: exchange.key ?? null,
    edge_id: record.diagramId,
    exchange_name: clean(exchange.name) || 'Interaction',
  };

  const communication = communicationForExchange(exchange);
  if (communication) {
    item.communication_mean = {
      source_participant_id: communication.edge.source,
      target_participant_id: communication.edge.target,
      edge_key: communication.edge.key ?? null,
      name: clean(communication.edge.name) || 'Communication',
    };
  }
  return item;
}

function communicationDiagramId(reference) {
  if (!reference || typeof reference !== 'object') return null;
  const match = edgeRecords('COMMUNICATION_MEAN').find(item => {
    if (item.edge.source !== reference.source_participant_id) return false;
    if (item.edge.target !== reference.target_participant_id) return false;
    if (reference.edge_key != null && String(item.edge.key) !== String(reference.edge_key)) return false;
    const wantedName = clean(reference.name);
    return !wantedName || clean(item.edge.name) === wantedName;
  });
  return match?.diagramId || null;
}

function selectionKeysForSteps(steps) {
  const keys = new Set();
  (Array.isArray(steps) ? steps : []).forEach(step => {
    if (!step || typeof step !== 'object') return;
    if (step.kind === 'activity' && step.activity_id) {
      keys.add(selectionKey('node', step.activity_id));
      return;
    }
    if (step.kind !== 'interaction') return;

    let interactionId = clean(step.edge_id);
    if (!interactionId) {
      const match = edgeRecords('OPERATIONAL_EXCHANGE').find(item => {
        if (item.edge.source !== step.source_activity_id || item.edge.target !== step.target_activity_id) return false;
        if (step.edge_key != null && String(item.edge.key) !== String(step.edge_key)) return false;
        const wantedName = clean(step.exchange_name);
        return !wantedName || clean(item.edge.name) === wantedName;
      });
      interactionId = match?.diagramId || '';
    }
    if (interactionId) keys.add(selectionKey('edge', interactionId));

    const communicationId = communicationDiagramId(step.communication_mean);
    if (communicationId) keys.add(selectionKey('edge', communicationId));
  });
  return keys;
}

function setScenarioHighlight(keys) {
  window.oaDiagram?.setMode('scenario');
  state.selected.clear();
  keys.forEach(key => state.selected.add(key));
  updateSelection();
}

function clearScenarioHighlight() {
  state.selected.clear();
  window.oaDiagram?.setMode('normal');
  updateSelection();
}

function validOutgoingRecords() {
  if (!authoring.active || !authoring.currentActivityId) return [];
  return edgeRecords('OPERATIONAL_EXCHANGE').filter(
    item => item.edge.source === authoring.currentActivityId
  );
}

function refreshValidHints() {
  document.querySelectorAll('.scenario-valid-next').forEach(node =>
    node.classList.remove('scenario-valid-next')
  );
  if (!authoring.active || !authoring.currentActivityId) return;
  validOutgoingRecords().forEach(record => {
    document.querySelectorAll(`[data-edge-id="${CSS.escape(record.diagramId)}"]`)
      .forEach(node => node.classList.add('scenario-valid-next'));
  });
}

function authoringInstruction() {
  if (!authoring.active) return '';
  if (!authoring.steps.length) {
    return `Scenario "${authoring.name}": select the first Operational Activity.`;
  }
  const current = nodeById(authoring.currentActivityId);
  const outgoing = validOutgoingRecords();
  if (!outgoing.length) {
    return `Scenario "${authoring.name}": ${clean(current?.name || authoring.currentActivityId)} has no outgoing interaction. Finish, undo, or cancel.`;
  }
  return `Scenario "${authoring.name}": select one outgoing interaction from ${clean(current?.name || authoring.currentActivityId)}. The destination activity will be selected automatically.`;
}

function updateScenarioStatus(message = '') {
  if (!el.status) return;
  el.status.textContent = message || authoringInstruction();
}

function syncAuthoringVisuals() {
  if (!authoring.active) return;
  setScenarioHighlight(selectionKeysForSteps(authoring.steps));
  refreshValidHints();
  updateScenarioStatus();
  renderAuthoringBar();
}

function deactivateSavedScenario() {
  activeScenarioId = null;
  clearScenarioHighlight();
  renderScenarioTray();
}

function activateSavedScenario(scenario) {
  if (authoring.active || !scenario?.valid) return;
  if (activeScenarioId === scenario.id) {
    deactivateSavedScenario();
    return;
  }
  activeScenarioId = scenario.id;
  setScenarioHighlight(selectionKeysForSteps(scenario.steps));
  renderScenarioTray();
  updateScenarioStatus(`Operational Scenario "${scenario.name}" is active. Click its block again to turn the highlight off.`);
}

function resetAuthoring({keepStatus = false} = {}) {
  authoring.active = false;
  authoring.name = '';
  authoring.steps = [];
  authoring.currentActivityId = null;
  authoring.submitting = false;
  edgeObserver?.disconnect();
  edgeObserver = null;
  clearScenarioHighlight();
  renderAuthoringBar();
  renderScenarioTray();
  updateCreateButton();
  if (!keepStatus && el.status) {
    el.status.textContent = 'Drag activities directly; drag participant containers from their header. Communication ports P can be moved up or down.';
  }
}

function beginAuthoring(name) {
  activeScenarioId = null;
  authoring.active = true;
  authoring.name = clean(name);
  authoring.steps = [];
  authoring.currentActivityId = null;
  authoring.submitting = false;
  setScenarioHighlight(new Set());

  edgeObserver?.disconnect();
  edgeObserver = new MutationObserver(() => requestAnimationFrame(refreshValidHints));
  if (el.edges) edgeObserver.observe(el.edges, {childList: true, subtree: true});

  renderScenarioTray();
  renderAuthoringBar();
  updateCreateButton();
  updateScenarioStatus();
}

function chooseStartActivity(activityId) {
  if (nodeById(activityId)?.type !== 'OperationalActivity') {
    updateScenarioStatus('Start the scenario by clicking an Operational Activity.');
    return;
  }
  authoring.steps = [activityStep(activityId)];
  authoring.currentActivityId = activityId;
  syncAuthoringVisuals();
}

function chooseInteraction(record) {
  if (!record || record.edge.type !== 'OPERATIONAL_EXCHANGE') return;
  if (record.edge.source !== authoring.currentActivityId) {
    updateScenarioStatus('That interaction does not start at the current scenario activity. Choose one of the highlighted outgoing interactions.');
    return;
  }
  if (nodeById(record.edge.target)?.type !== 'OperationalActivity') {
    updateScenarioStatus('That interaction does not lead to a confirmed Operational Activity.');
    return;
  }

  authoring.steps.push(interactionStep(record));
  authoring.steps.push(activityStep(record.edge.target));
  authoring.currentActivityId = record.edge.target;
  syncAuthoringVisuals();
}

function undoAuthoringStep() {
  if (!authoring.active || authoring.submitting) return;
  if (authoring.steps.length >= 3) {
    authoring.steps.splice(-2);
  } else if (authoring.steps.length === 1) {
    authoring.steps = [];
  }
  const lastActivity = [...authoring.steps].reverse()
    .find(step => step.kind === 'activity');
  authoring.currentActivityId = lastActivity?.activity_id || null;
  syncAuthoringVisuals();
}

async function finishAuthoring() {
  if (!authoring.active || authoring.submitting || authoring.steps.length < 3) return;
  authoring.submitting = true;
  renderAuthoringBar();
  updateScenarioStatus('Saving Operational Scenario…');

  try {
    const response = await fetch('/api/scenario/create', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        name: authoring.name,
        steps: authoring.steps,
      }),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok || !data.scenario) {
      authoring.submitting = false;
      renderAuthoringBar();
      updateScenarioStatus(data.error || 'The Operational Scenario could not be saved.');
      return;
    }

    const completed = data.scenario;
    authoring.active = false;
    authoring.submitting = false;
    authoring.steps = [];
    authoring.currentActivityId = null;
    authoring.name = '';
    activeScenarioId = completed.id;
    edgeObserver?.disconnect();
    edgeObserver = null;

    const currentScenarios = scenarioList().filter(item => item.id !== completed.id);
    latestModel = {
      ...latestModel,
      scenarios: [...currentScenarios, {...completed, valid: true, issues: []}],
    };
    renderAuthoringBar();
    renderScenarioTray();
    updateCreateButton();
    setScenarioHighlight(selectionKeysForSteps(completed.steps));
    updateScenarioStatus(`Operational Scenario "${completed.name}" was saved and is active.`);

    if (typeof window.pollState === 'function') {
      await window.pollState({force: true});
    }
  } catch (_error) {
    authoring.submitting = false;
    renderAuthoringBar();
    updateScenarioStatus('Connection to the local app was interrupted while saving the scenario.');
  }
}

function cancelAuthoring() {
  if (!authoring.active || authoring.submitting) return;
  resetAuthoring();
}

function onScenarioDiagramClick(event) {
  if (!authoring.active) return;
  const selectable = event.target.closest('[data-oa-select-key]');
  if (!selectable) return;

  event.preventDefault();
  event.stopPropagation();
  event.stopImmediatePropagation();

  if (Date.now() < state.suppressClickUntil) return;

  const key = selectable.dataset.oaSelectKey || '';
  const split = key.indexOf(':');
  const kind = split >= 0 ? key.slice(0, split) : '';
  const id = split >= 0 ? key.slice(split + 1) : '';

  if (!authoring.steps.length) {
    if (kind === 'node') chooseStartActivity(id);
    else updateScenarioStatus('Start the scenario by clicking an Operational Activity.');
    return;
  }

  if (kind !== 'edge' || selectable.dataset.edgeType !== 'OPERATIONAL_EXCHANGE') {
    updateScenarioStatus('Continue the scenario by clicking one valid outgoing Operational Interaction.');
    return;
  }

  chooseInteraction(exchangeByDiagramId(id));
}

function createElement(tag, className = '', text = '') {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text) node.textContent = text;
  return node;
}

let createButton = null;
let authoringBar = null;
let scenarioTray = null;
let modal = null;

function renderAuthoringBar() {
  if (!authoringBar) return;
  authoringBar.hidden = !authoring.active;
  if (!authoring.active) {
    authoringBar.innerHTML = '';
    return;
  }

  authoringBar.innerHTML = '';
  const copy = createElement('div', 'oa-scenario-authoring-copy');
  const title = createElement('strong', '', authoring.name);
  const count = createElement(
    'span',
    '',
    `${authoring.steps.filter(step => step.kind === 'activity').length} activities · ${authoring.steps.filter(step => step.kind === 'interaction').length} interactions`
  );
  copy.append(title, count);

  const actions = createElement('div', 'oa-scenario-authoring-actions');
  const undo = createElement('button', 'oa-diagram-tool', 'Undo last step');
  undo.type = 'button';
  undo.disabled = authoring.submitting || !authoring.steps.length;
  undo.addEventListener('click', undoAuthoringStep);

  const finish = createElement('button', 'oa-diagram-tool oa-scenario-finish', authoring.submitting ? 'Saving…' : 'Finish Scenario');
  finish.type = 'button';
  finish.disabled = authoring.submitting || authoring.steps.length < 3;
  finish.addEventListener('click', finishAuthoring);

  const cancel = createElement('button', 'oa-diagram-tool', 'Cancel');
  cancel.type = 'button';
  cancel.disabled = authoring.submitting;
  cancel.addEventListener('click', cancelAuthoring);

  actions.append(undo, finish, cancel);
  authoringBar.append(copy, actions);
}

function renderScenarioTray() {
  if (!scenarioTray) return;
  scenarioTray.innerHTML = '';

  const scenarios = scenarioList();
  if (!scenarios.length) {
    scenarioTray.hidden = true;
    return;
  }

  scenarioTray.hidden = false;
  const label = createElement('div', 'oa-scenario-tray-label', 'Operational Scenarios');
  scenarioTray.appendChild(label);

  scenarios.forEach(scenario => {
    const button = createElement('button', 'oa-scenario-block');
    button.type = 'button';
    button.dataset.scenarioId = scenario.id || '';
    button.classList.toggle('active', activeScenarioId === scenario.id);
    button.classList.toggle('invalid', scenario.valid === false);
    button.setAttribute('aria-pressed', activeScenarioId === scenario.id ? 'true' : 'false');
    button.disabled = authoring.active || scenario.valid === false;

    const kind = createElement('span', 'oa-scenario-block-kind', 'Operational Scenario');
    const name = createElement('strong', 'oa-scenario-block-name', scenario.name || scenario.id || 'Scenario');
    button.append(kind, name);

    if (scenario.valid === false) {
      const issues = Array.isArray(scenario.issues) ? scenario.issues.join(' ') : 'Scenario references are invalid.';
      button.title = issues;
    } else {
      button.title = activeScenarioId === scenario.id
        ? 'Click to turn this scenario highlight off'
        : 'Click to highlight this scenario';
      button.addEventListener('click', () => activateSavedScenario(scenario));
    }
    scenarioTray.appendChild(button);
  });
}

function updateCreateButton() {
  if (!createButton) return;
  const hasActivity = modelNodes().some(node => node.type === 'OperationalActivity');
  const hasExchange = modelEdges().some(edge => edge.type === 'OPERATIONAL_EXCHANGE');
  createButton.disabled = authoring.active || !latestWaiting || !hasActivity || !hasExchange;
  createButton.title = !latestWaiting
    ? 'Wait until the current modeling step is ready'
    : !hasActivity || !hasExchange
      ? 'Create at least two connected Operational Activities first'
      : 'Create an Operational Scenario directly on the diagram';
}

function openNameModal() {
  if (!modal || createButton?.disabled) return;
  const input = modal.querySelector('input');
  const message = modal.querySelector('.oa-scenario-modal-message');
  message.textContent = '';
  input.value = '';
  modal.hidden = false;
  requestAnimationFrame(() => input.focus());
}

function closeNameModal() {
  if (!modal) return;
  modal.hidden = true;
  createButton?.focus();
}

function submitNameModal() {
  const input = modal?.querySelector('input');
  const message = modal?.querySelector('.oa-scenario-modal-message');
  const name = clean(input?.value);
  if (!name) {
    if (message) message.textContent = 'Enter a scenario name.';
    input?.focus();
    return;
  }
  const duplicate = scenarioList().some(
    scenario => clean(scenario.name).toLowerCase() === name.toLowerCase()
  );
  if (duplicate) {
    if (message) message.textContent = 'A scenario with that name already exists.';
    input?.focus();
    return;
  }
  closeNameModal();
  beginAuthoring(name);
}

function installScenarioUi() {
  if (!el.tab || !el.viewport) return false;

  const tools = el.tab.querySelector('.oa-diagram-tools');
  if (tools && !document.getElementById('oaCreateScenario')) {
    createButton = createElement('button', 'oa-diagram-tool oa-scenario-create', 'Create Operational Scenario');
    createButton.id = 'oaCreateScenario';
    createButton.type = 'button';
    createButton.addEventListener('click', openNameModal);
    tools.appendChild(createButton);
  } else {
    createButton = document.getElementById('oaCreateScenario');
  }

  if (!document.getElementById('oaScenarioAuthoringBar')) {
    authoringBar = createElement('div', 'oa-scenario-authoring-bar');
    authoringBar.id = 'oaScenarioAuthoringBar';
    authoringBar.hidden = true;
    const toolbar = el.tab.querySelector('.oa-diagram-toolbar');
    toolbar?.insertAdjacentElement('afterend', authoringBar);
  } else {
    authoringBar = document.getElementById('oaScenarioAuthoringBar');
  }

  if (!document.getElementById('oaScenarioTray')) {
    scenarioTray = createElement('div', 'oa-scenario-tray');
    scenarioTray.id = 'oaScenarioTray';
    scenarioTray.hidden = true;
    el.tab.appendChild(scenarioTray);
  } else {
    scenarioTray = document.getElementById('oaScenarioTray');
  }

  if (!document.getElementById('oaScenarioModal')) {
    modal = createElement('div', 'oa-scenario-modal');
    modal.id = 'oaScenarioModal';
    modal.hidden = true;
    modal.innerHTML = `
      <div class="oa-scenario-modal-backdrop" data-scenario-close></div>
      <div class="oa-scenario-modal-card" role="dialog" aria-modal="true" aria-labelledby="oaScenarioModalTitle">
        <div class="oa-scenario-modal-accent"></div>
        <h2 id="oaScenarioModalTitle">Create Operational Scenario</h2>
        <p>Name the scenario, then select its path directly on the Operational Analysis diagram.</p>
        <label for="oaScenarioName">Scenario name</label>
        <input id="oaScenarioName" type="text" maxlength="120" autocomplete="off" placeholder="Example: Nominal operation">
        <p class="oa-scenario-modal-message" aria-live="polite"></p>
        <div class="oa-scenario-modal-actions">
          <button type="button" class="secondary-button" data-scenario-close>Cancel</button>
          <button type="button" class="primary-button" data-scenario-start>Start selecting</button>
        </div>
      </div>`;
    document.body.appendChild(modal);
    modal.querySelectorAll('[data-scenario-close]').forEach(button =>
      button.addEventListener('click', closeNameModal)
    );
    modal.querySelector('[data-scenario-start]')?.addEventListener('click', submitNameModal);
    modal.querySelector('input')?.addEventListener('keydown', event => {
      if (event.key === 'Enter') {
        event.preventDefault();
        submitNameModal();
      }
    });
  } else {
    modal = document.getElementById('oaScenarioModal');
  }

  el.viewport.addEventListener('click', onScenarioDiagramClick, {capture: true});
  window.addEventListener('pointerup', () => {
    if (authoring.active) requestAnimationFrame(refreshValidHints);
  }, {capture: true});
  renderAuthoringBar();
  renderScenarioTray();
  updateCreateButton();
  return true;
}

function renderScenarioPseudoCode(model) {
  const root = document.getElementById('modelTextual');
  if (!root) return;
  root.querySelector('.operational-scenarios-section')?.remove();

  const scenarios = scenarioList(model);
  if (!scenarios.length) return;
  const nodes = new Map((model.nodes || []).map(node => [node.id, node]));

  const section = createElement('section', 'tree-section operational-scenarios-section');
  section.appendChild(createElement('h3', '', 'Operational Scenarios'));

  scenarios.forEach(scenario => {
    const item = createElement('div', 'tree-item oa-scenario-text-item');
    const name = createElement('div', 'tree-item-name', scenario.name || scenario.id || 'Scenario');
    item.appendChild(name);

    const code = createElement('pre', 'oa-scenario-pseudocode');
    const lines = [`scenario "${scenario.name || scenario.id || 'Scenario'}"`];
    const steps = Array.isArray(scenario.steps) ? scenario.steps : [];
    const first = steps.find(step => step.kind === 'activity');
    if (first) {
      lines.push(`  start "${nodes.get(first.activity_id)?.name || first.activity_id}"`);
    }
    steps.filter(step => step.kind === 'interaction').forEach(step => {
      const source = nodes.get(step.source_activity_id)?.name || step.source_activity_id;
      const target = nodes.get(step.target_activity_id)?.name || step.target_activity_id;
      const exchange = step.exchange_name || 'Interaction';
      const via = step.communication_mean?.name
        ? ` via "${step.communication_mean.name}"`
        : '';
      lines.push(`  "${source}" -- "${exchange}"${via} --> "${target}"`);
    });
    if (scenario.valid === false) {
      lines.push('  // INVALID: one or more referenced model elements no longer exist');
    }
    code.textContent = lines.join('\n');
    item.appendChild(code);
    section.appendChild(item);
  });

  root.appendChild(section);
}

function installTextProjectionWrapper() {
  if (typeof window.renderRevisionTextualModel !== 'function') return;
  const prior = window.renderRevisionTextualModel;
  if (prior.__oaScenarioWrapped) return;

  const wrapped = function scenarioAwareTextProjection(model) {
    prior(model);
    renderScenarioPseudoCode(model);
  };
  wrapped.__oaScenarioWrapped = true;
  window.renderRevisionTextualModel = wrapped;
}

function applyScenarioState(nextState) {
  const nextSession = String(nextState?.session_id || '');
  if (latestSession && nextSession && nextSession !== latestSession) {
    authoring.active = false;
    authoring.name = '';
    authoring.steps = [];
    authoring.currentActivityId = null;
    authoring.submitting = false;
    activeScenarioId = null;
    edgeObserver?.disconnect();
    edgeObserver = null;
  }
  latestSession = nextSession || latestSession;
  latestWaiting = Boolean(nextState?.waiting) && !nextState?.closed;
  latestModel = nextState?.model || {nodes: [], drafts: [], edges: [], scenarios: []};

  renderScenarioTray();
  updateCreateButton();
  renderScenarioPseudoCode(latestModel);

  if (authoring.active) {
    syncAuthoringVisuals();
    return;
  }
  if (activeScenarioId) {
    const active = scenarioList().find(item => item.id === activeScenarioId && item.valid !== false);
    if (active) {
      setScenarioHighlight(selectionKeysForSteps(active.steps));
      renderScenarioTray();
    } else {
      activeScenarioId = null;
      clearScenarioHighlight();
      renderScenarioTray();
    }
  }
}

function wrapApplyState() {
  if (typeof window.applyState !== 'function') return;
  const prior = window.applyState;
  if (prior.__oaScenarioWrapped) return;
  const wrapped = function scenarioAwareApplyState(nextState) {
    prior(nextState);
    applyScenarioState(nextState);
  };
  wrapped.__oaScenarioWrapped = true;
  window.applyState = wrapped;
}

function init() {
  ensureStyles();
  installTextProjectionWrapper();
  wrapApplyState();

  const installed = installScenarioUi();
  if (!installed) {
    requestAnimationFrame(init);
    return;
  }

  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && modal && !modal.hidden) {
      closeNameModal();
      return;
    }
    if (event.key === 'Escape' && authoring.active && !authoring.submitting) {
      cancelAuthoring();
    }
  });

  if (typeof window.pollState === 'function') {
    window.pollState({force: true});
  }
}

init();
