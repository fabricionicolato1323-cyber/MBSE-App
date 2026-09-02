const chat = document.getElementById('chat');
const quickActions = document.getElementById('quickActions');
const composer = document.getElementById('composer');
const input = document.getElementById('messageInput');
const sendButton = document.getElementById('sendButton');
const statusLine = document.getElementById('statusLine');
const modelCount = document.getElementById('modelCount');
const diagram = document.getElementById('modelDiagram');
const emptyModel = document.getElementById('emptyModel');
const details = document.getElementById('modelDetails');
const resetModal = document.getElementById('resetModal');
const resetButton = document.getElementById('resetButton');
const cancelResetButton = document.getElementById('cancelResetButton');
const confirmResetButton = document.getElementById('confirmResetButton');

let lastTurnsSignature = '';
let busy = true;
let activeSessionId = null;
let stateRequest = null;
let stateRequestSerial = 0;
let startingNewModel = false;

const friendlyType = (type) => ({
  OperationalCapability: 'Goal',
  OperationalActor: 'Person / role',
  OperationalEntity: 'Participant / context',
  OperationalActivity: 'Action',
  Pending: 'Temporary input'
}[type] || type || 'Item');

const friendlyRelation = (type) => ({
  PERFORMS: 'performs',
  SUPPORTS_CAPABILITY: 'supports',
  OPERATIONAL_EXCHANGE: 'exchange',
  COMMUNICATION_MEAN: 'communication',
  CONTAINS: 'contains',
  LOCATED_IN: 'located in',
  DECOMPOSES: 'breaks down into'
}[type] || (type || '').toLowerCase().replaceAll('_', ' '));

function turnsSignature(turns) {
  return turns.map(turn => `${turn.id}:${turn.role}`).join('|');
}

function renderTurns(turns) {
  const signature = turnsSignature(turns);
  if (signature === lastTurnsSignature) return;
  lastTurnsSignature = signature;
  chat.innerHTML = '';
  turns.forEach(turn => {
    const row = document.createElement('div');
    row.className = `message-row ${turn.role}`;
    const bubble = document.createElement('div');
    bubble.className = 'message-bubble';
    bubble.textContent = turn.content;
    row.appendChild(bubble);
    chat.appendChild(row);
  });
  chat.scrollTop = chat.scrollHeight;
}

function renderActions(buttons, waiting) {
  quickActions.innerHTML = '';
  buttons.forEach(button => {
    const element = document.createElement('button');
    element.type = 'button';
    element.textContent = button.label;
    element.disabled = !waiting;
    element.addEventListener('click', () => sendValue(button.value, button.label));
    quickActions.appendChild(element);
  });
}

function escapeSvgText(value, max = 26) {
  const clean = String(value || '').replace(/\s+/g, ' ').trim();
  return clean.length > max ? `${clean.slice(0, max - 1)}…` : clean;
}

function diagramLayout(nodes) {
  const order = ['OperationalCapability', 'OperationalActor', 'OperationalEntity', 'OperationalActivity', 'Pending'];
  const groups = new Map();
  nodes.forEach(node => {
    const key = node.type || 'Other';
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(node);
  });

  const layout = new Map();
  let y = 28;
  order.concat([...groups.keys()].filter(k => !order.includes(k))).forEach(type => {
    const group = groups.get(type) || [];
    group.forEach(node => {
      layout.set(node.id, {x: 30, y, width: 350, height: 56});
      y += 78;
    });
  });
  return {layout, height: Math.max(680, y + 30)};
}

function renderDiagram(model) {
  const nodes = [...(model.nodes || []), ...(model.drafts || [])];
  const edges = model.edges || [];
  emptyModel.style.display = nodes.length ? 'none' : 'block';
  const {layout, height} = diagramLayout(nodes);
  diagram.setAttribute('viewBox', `0 0 420 ${height}`);
  diagram.innerHTML = `
    <defs>
      <marker id="arrow" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto">
        <path d="M0,0 L0,6 L7,3 z" class="arrow-head"></path>
      </marker>
    </defs>`;

  edges.forEach(edge => {
    const source = layout.get(edge.source);
    const target = layout.get(edge.target);
    if (!source || !target) return;
    const x1 = source.x + source.width / 2;
    const y1 = source.y + source.height;
    const x2 = target.x + target.width / 2;
    const y2 = target.y;
    const mid = (y1 + y2) / 2;
    const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    path.setAttribute('class', 'edge-line');
    path.setAttribute('d', `M ${x1} ${y1} C ${x1} ${mid}, ${x2} ${mid}, ${x2} ${y2}`);
    diagram.appendChild(path);

    const label = document.createElementNS('http://www.w3.org/2000/svg', 'text');
    label.setAttribute('class', 'edge-label');
    label.setAttribute('x', String(x1 + 8));
    label.setAttribute('y', String(mid - 3));
    label.textContent = edge.name || friendlyRelation(edge.type);
    diagram.appendChild(label);
  });

  nodes.forEach(node => {
    const pos = layout.get(node.id);
    const group = document.createElementNS('http://www.w3.org/2000/svg', 'g');
    group.setAttribute('class', `node-card ${node.status === 'temporary' ? 'temporary' : ''}`);
    const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
    rect.setAttribute('x', pos.x);
    rect.setAttribute('y', pos.y);
    rect.setAttribute('width', pos.width);
    rect.setAttribute('height', pos.height);
    group.appendChild(rect);

    const title = document.createElementNS('http://www.w3.org/2000/svg', 'text');
    title.setAttribute('class', 'title');
    title.setAttribute('x', pos.x + 14);
    title.setAttribute('y', pos.y + 23);
    title.textContent = escapeSvgText(node.name || node.id, 42);
    group.appendChild(title);

    const type = document.createElementNS('http://www.w3.org/2000/svg', 'text');
    type.setAttribute('class', 'type');
    type.setAttribute('x', pos.x + 14);
    type.setAttribute('y', pos.y + 42);
    type.textContent = `${friendlyType(node.type)} · ${node.status === 'temporary' ? 'temporary' : 'confirmed'}`;
    group.appendChild(type);
    diagram.appendChild(group);
  });
}

function renderDetails(model) {
  const nodes = [...(model.nodes || []), ...(model.drafts || [])];
  const byType = new Map();
  nodes.forEach(node => {
    const label = friendlyType(node.type);
    if (!byType.has(label)) byType.set(label, []);
    byType.get(label).push(node);
  });
  details.innerHTML = '';
  byType.forEach((items, label) => {
    const group = document.createElement('section');
    group.className = 'detail-group';
    const heading = document.createElement('h3');
    heading.textContent = label;
    group.appendChild(heading);
    items.forEach(item => {
      const card = document.createElement('div');
      card.className = `detail-item ${item.status === 'temporary' ? 'temporary' : ''}`;
      const name = document.createElement('div');
      name.className = 'detail-name';
      name.textContent = item.name || item.id;
      const meta = document.createElement('div');
      meta.className = 'detail-meta';
      const characteristicCount = Array.isArray(item.characteristics) ? item.characteristics.length : 0;
      meta.textContent = `${item.status === 'temporary' ? 'Temporary' : 'Confirmed'}${characteristicCount ? ` · ${characteristicCount} characteristic(s)` : ''}`;
      card.append(name, meta);
      group.appendChild(card);
    });
    details.appendChild(group);
  });

  if ((model.edges || []).length) {
    const group = document.createElement('section');
    group.className = 'detail-group';
    const heading = document.createElement('h3');
    heading.textContent = 'Connections';
    group.appendChild(heading);
    model.edges.forEach(edge => {
      const source = (model.nodes || []).find(n => n.id === edge.source);
      const target = (model.nodes || []).find(n => n.id === edge.target);
      const card = document.createElement('div');
      card.className = 'detail-item';
      const name = document.createElement('div');
      name.className = 'detail-name';
      name.textContent = edge.name || friendlyRelation(edge.type);
      const meta = document.createElement('div');
      meta.className = 'detail-meta';
      meta.textContent = `${source?.name || edge.source} → ${target?.name || edge.target}`;
      card.append(name, meta);
      group.appendChild(card);
    });
    details.appendChild(group);
  }
}

function setBusy(value, message = null) {
  busy = value;
  sendButton.disabled = value;
  input.disabled = value;
  if (message !== null) {
    statusLine.textContent = message;
  } else {
    statusLine.textContent = value ? 'Processing…' : 'Ready';
  }
}

function clearRenderedSession() {
  lastTurnsSignature = '';
  chat.innerHTML = '';
  quickActions.innerHTML = '';
  details.innerHTML = '';
  diagram.innerHTML = '';
  emptyModel.style.display = 'block';
  modelCount.textContent = '0 items · 0 links';
}

function applyState(state) {
  if (!state.session_id) return;
  if (activeSessionId && state.session_id !== activeSessionId) return;

  if (!activeSessionId) activeSessionId = state.session_id;
  renderTurns(state.turns || []);
  renderActions(state.buttons || [], state.waiting);
  renderDiagram(state.model || {});
  renderDetails(state.model || {});

  const counts = state.model?.counts || {nodes: 0, edges: 0};
  const drafts = state.model?.drafts?.length || 0;
  modelCount.textContent = `${counts.nodes} items · ${counts.edges} links${drafts ? ` · ${drafts} temporary` : ''}`;

  if (startingNewModel && state.waiting && (state.turns || []).length) {
    startingNewModel = false;
  }

  if (state.closed) {
    setBusy(true, 'Modeling session finished.');
  } else if (startingNewModel) {
    setBusy(true, 'Starting new model…');
  } else {
    setBusy(!state.waiting);
  }
}

async function pollState({force = false} = {}) {
  if (stateRequest && !force) return;

  if (force && stateRequest) {
    stateRequest.controller.abort();
  }

  const serial = ++stateRequestSerial;
  const controller = new AbortController();
  stateRequest = {serial, controller};

  try {
    const response = await fetch('/api/state', {
      cache: 'no-store',
      signal: controller.signal
    });

    if (response.status === 409) return;
    if (!response.ok) throw new Error(`State request failed: ${response.status}`);

    const state = await response.json();
    if (!stateRequest || stateRequest.serial !== serial) return;
    applyState(state);
  } catch (error) {
    if (error.name !== 'AbortError') {
      statusLine.textContent = 'Connection to the local app was interrupted.';
    }
  } finally {
    if (stateRequest && stateRequest.serial === serial) {
      stateRequest = null;
    }
  }
}

async function sendValue(value, displayValue = null) {
  if (busy) return;
  setBusy(true);

  const response = await fetch('/api/input', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({value, display_value: displayValue})
  });

  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    statusLine.textContent = data.error || 'The input could not be sent.';
    setBusy(false, statusLine.textContent);
    return;
  }

  input.value = '';
  await pollState({force: true});
}

async function sendCommand(command) {
  if (busy) return;
  setBusy(true);

  const response = await fetch('/api/command', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({command})
  });

  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    statusLine.textContent = data.error || 'The command could not be sent.';
    setBusy(false, statusLine.textContent);
    return;
  }

  await pollState({force: true});
}

function openResetModal() {
  resetModal.hidden = false;
  confirmResetButton.focus();
}

function closeResetModal() {
  resetModal.hidden = true;
  resetButton.focus();
}

async function startNewModel() {
  closeResetModal();
  startingNewModel = true;
  setBusy(true, 'Starting new model…');

  if (stateRequest) {
    stateRequest.controller.abort();
    stateRequest = null;
  }

  const response = await fetch('/api/reset', {method: 'POST'});
  const data = await response.json().catch(() => ({}));

  if (!response.ok || !data.session_id) {
    startingNewModel = false;
    setBusy(false, data.error || 'A new model could not be started.');
    return;
  }

  activeSessionId = data.session_id;
  clearRenderedSession();
  await pollState({force: true});
}

composer.addEventListener('submit', event => {
  event.preventDefault();
  const value = input.value.trim();
  if (value) sendValue(value);
});

input.addEventListener('keydown', event => {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault();
    composer.requestSubmit();
  }
});

document.getElementById('commandBar').addEventListener('click', event => {
  const command = event.target.dataset.command;
  if (command) sendCommand(command);
});

resetButton.addEventListener('click', openResetModal);
cancelResetButton.addEventListener('click', closeResetModal);
confirmResetButton.addEventListener('click', startNewModel);
resetModal.querySelector('[data-close-reset]').addEventListener('click', closeResetModal);

document.addEventListener('keydown', event => {
  if (event.key === 'Escape' && !resetModal.hidden) closeResetModal();
});

document.querySelectorAll('.tab-button').forEach(button => {
  button.addEventListener('click', () => {
    document.querySelectorAll('.tab-button').forEach(item => item.classList.toggle('active', item === button));
    document.querySelectorAll('.tab-content').forEach(content => content.classList.remove('active'));
    document.getElementById(button.dataset.tab === 'diagram' ? 'diagramTab' : 'detailsTab').classList.add('active');
  });
});

setInterval(() => pollState(), 600);
pollState({force: true});
