import {PARTICIPANTS, state, clean, typeName, selectionKey, edgeId, isVisibleNode,
  visibleLayoutEntries, expandAllContainers} from './oa_diagram_v2_state.js';

export const el = {};
const SVG_NS = 'http://www.w3.org/2000/svg';

export function installMarkup() {
  const tab = document.getElementById('diagramTab');
  if (!tab || document.getElementById('oaDiagramViewport')) return;
  tab.querySelector('.diagram-placeholder')?.remove();
  const toolbar = document.createElement('div'); toolbar.className = 'oa-diagram-toolbar';
  toolbar.innerHTML = `<div class="oa-diagram-tools">
    <button id="oaDiagramZoomOut" class="oa-diagram-tool" type="button" aria-label="Zoom out">−</button>
    <button id="oaDiagramZoomIn" class="oa-diagram-tool" type="button" aria-label="Zoom in">+</button>
    <button id="oaDiagramFit" class="oa-diagram-tool" type="button">Fit</button>
    <button id="oaDiagramReset" class="oa-diagram-tool" type="button">Reset layout</button>
    <button id="oaDiagramCapabilitiesToggle" class="oa-diagram-tool oa-diagram-toggle" type="button" aria-pressed="true">Capabilities: On</button>
  </div><span id="oaDiagramMode" class="oa-diagram-mode-label">Normal selection</span>`;
  const viewport = document.createElement('div'); viewport.id = 'oaDiagramViewport'; viewport.className = 'oa-diagram-viewport';
  viewport.tabIndex = 0; viewport.setAttribute('aria-label', 'Interactive Operational Analysis diagram');
  viewport.innerHTML = `<div id="oaDiagramScene" class="oa-diagram-scene">
    <svg id="oaDiagramEdges" class="oa-diagram-edges" aria-label="Model connections"></svg>
    <div id="oaDiagramNodes" class="oa-diagram-nodes"></div><div id="oaDiagramPorts" class="oa-diagram-ports"></div>
  </div><div id="oaDiagramEmpty" class="oa-diagram-empty">The diagram will appear here as the model is built.</div>`;
  const status = document.createElement('div'); status.id = 'oaDiagramStatus'; status.className = 'oa-diagram-selection-status';
  status.setAttribute('aria-live', 'polite'); status.textContent = 'Drag blocks to organize the diagram. Ctrl/Cmd-click keeps multiple elements selected.';
  const legacy = tab.querySelector('.legacy-diagram-layer'); tab.insertBefore(toolbar, legacy); tab.insertBefore(viewport, legacy); tab.insertBefore(status, legacy);
}

export function bindElements() {
  Object.assign(el, {tab: document.getElementById('diagramTab'), viewport: document.getElementById('oaDiagramViewport'),
    scene: document.getElementById('oaDiagramScene'), edges: document.getElementById('oaDiagramEdges'),
    nodes: document.getElementById('oaDiagramNodes'), ports: document.getElementById('oaDiagramPorts'),
    empty: document.getElementById('oaDiagramEmpty'), status: document.getElementById('oaDiagramStatus'),
    mode: document.getElementById('oaDiagramMode'), capabilities: document.getElementById('oaDiagramCapabilitiesToggle')});
  return !!(el.tab && el.viewport && el.scene && el.edges && el.nodes && el.ports);
}

export function updateCapabilityButton() {
  if (!el.capabilities) return;
  el.capabilities.textContent = `Capabilities: ${state.showCapabilities ? 'On' : 'Off'}`;
  el.capabilities.setAttribute('aria-pressed', state.showCapabilities ? 'true' : 'false');
  el.capabilities.classList.toggle('active', state.showCapabilities);
}

export function updateSelection() {
  document.querySelectorAll('[data-oa-select-key]').forEach(node => {
    const selected = state.selected.has(node.dataset.oaSelectKey); node.classList.toggle('selected', selected);
    node.setAttribute('aria-pressed', selected ? 'true' : 'false');
  });
  const selected = selectionPayload();
  if (el.status) {
    if (selected.length) el.status.textContent = `${selected.length} diagram element${selected.length === 1 ? '' : 's'} selected.`;
    else if (state.invalidContainments.length) el.status.textContent = 'Invalid containment kept outside actor: Operational Actors cannot contain Operational Entities.';
    else el.status.textContent = state.mode === 'scenario' ? 'Scenario selection mode: click elements to add or remove them.' : 'Drag blocks to organize the diagram. Ctrl/Cmd-click keeps multiple elements selected.';
  }
  window.dispatchEvent(new CustomEvent('oa:diagram-selection-change', {detail: {mode: state.mode, selected}}));
}

export function select(kind, id, event) {
  if (Date.now() < state.suppressClickUntil) return;
  const key = selectionKey(kind, id), additive = state.mode === 'scenario' || event?.ctrlKey || event?.metaKey;
  if (!additive) state.selected.clear();
  if (additive && state.selected.has(key)) state.selected.delete(key); else state.selected.add(key);
  updateSelection();
}
export const selectionPayload = () => [...state.selected].map(key => { const i = key.indexOf(':'); return {kind: key.slice(0, i), id: key.slice(i + 1)}; });

export function updateBounds() {
  let maxX = 1200, maxY = 800;
  for (const [, p] of visibleLayoutEntries()) { maxX = Math.max(maxX, p.x + p.w + 140); maxY = Math.max(maxY, p.y + p.h + 140); }
  el.scene.style.width = `${maxX}px`; el.scene.style.height = `${maxY}px`;
  el.edges.setAttribute('width', String(maxX)); el.edges.setAttribute('height', String(maxY)); el.edges.setAttribute('viewBox', `0 0 ${maxX} ${maxY}`);
}
export const applyView = () => { el.scene.style.transform = `translate(${state.view.x}px, ${state.view.y}px) scale(${state.view.zoom})`; };

function nodeElement(node) {
  const p = state.layout.get(node.id), div = document.createElement('div');
  div.className = `oa-diagram-node type-${clean(node.type).toLowerCase()} ${node.status === 'temporary' ? 'temporary' : 'confirmed'} ${PARTICIPANTS.has(node.type) ? 'participant-container' : 'leaf-node'}`;
  div.dataset.nodeId = node.id; div.dataset.oaSelectKey = selectionKey('node', node.id); div.tabIndex = 0;
  div.setAttribute('role', 'button'); div.setAttribute('aria-pressed', 'false');
  Object.assign(div.style, {left: `${p.x}px`, top: `${p.y}px`, width: `${p.w}px`, height: `${p.h}px`});
  div.innerHTML = `<div class="oa-diagram-node-header"><span class="oa-diagram-node-type">${typeName(node.type)}</span><strong class="oa-diagram-node-title">${clean(node.name || node.id)}</strong></div>`;
  if (PARTICIPANTS.has(node.type)) { const hint = document.createElement('small'); hint.className = 'oa-diagram-containment-hint';
    hint.textContent = node.type === 'OperationalActor' ? 'actors + activities' : 'entities + actors + activities'; div.appendChild(hint); }
  const resize = document.createElement('button'); resize.type = 'button'; resize.className = 'oa-diagram-resize-handle'; resize.textContent = '↘';
  resize.setAttribute('aria-label', `Resize ${clean(node.name || node.id)}`); div.appendChild(resize);
  div.addEventListener('click', event => { if (!event.target.closest('.oa-diagram-resize-handle')) select('node', node.id, event); });
  div.addEventListener('keydown', event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); select('node', node.id, event); } });
  return div;
}

export function renderNodes() {
  el.nodes.innerHTML = '';
  [...state.byId.values()].filter(isVisibleNode).forEach(node => el.nodes.appendChild(nodeElement(node)));
}

function svg(name, attrs = {}) { const node = document.createElementNS(SVG_NS, name); Object.entries(attrs).forEach(([k, v]) => node.setAttribute(k, String(v))); return node; }
function center(id) { const p = state.layout.get(id); return p ? {x: p.x + p.w / 2, y: p.y + p.h / 2} : null; }
function curve(a, b) { const bend = Math.max(45, Math.abs(b.x - a.x) * .4), dir = b.x >= a.x ? 1 : -1; return `M ${a.x} ${a.y} C ${a.x + bend * dir} ${a.y}, ${b.x - bend * dir} ${b.y}, ${b.x} ${b.y}`; }
function anchor(id, toward) { const p = state.layout.get(id), c = center(id), t = center(toward); if (!p || !c || !t) return null;
  if (Math.abs(t.x - c.x) >= Math.abs(t.y - c.y)) return {x: t.x >= c.x ? p.x + p.w : p.x, y: c.y}; return {x: c.x, y: t.y >= c.y ? p.y + p.h : p.y}; }
function anchorToPoint(id, point) { const p = state.layout.get(id), c = center(id); if (!p || !c || !point) return null;
  if (Math.abs(point.x - c.x) >= Math.abs(point.y - c.y)) return {x: point.x >= c.x ? p.x + p.w : p.x, y: c.y}; return {x: c.x, y: point.y >= c.y ? p.y + p.h : p.y}; }
function addEdgeInteraction(node, id) { node.dataset.oaSelectKey = selectionKey('edge', id); node.setAttribute('role', 'button'); node.setAttribute('tabindex', '0'); node.setAttribute('aria-pressed', 'false');
  node.addEventListener('click', event => { event.stopPropagation(); select('edge', id, event); }); }
function addPort(id, participantId, x, y) { const port = document.createElement('button'); port.type = 'button'; port.className = 'oa-diagram-port'; port.textContent = 'P';
  port.dataset.oaSelectKey = selectionKey('port', id); port.setAttribute('aria-pressed', 'false'); Object.assign(port.style, {left: `${x - 11}px`, top: `${y - 11}px`});
  port.setAttribute('aria-label', `Communication port on ${clean(state.byId.get(participantId)?.name || participantId)}`); port.addEventListener('click', e => { e.stopPropagation(); select('port', id, e); }); el.ports.appendChild(port); }

const communicationMatches = (cm, a, b) => (cm.source === a && cm.target === b) || (cm.source === b && cm.target === a);
function communicationForExchange(edge) {
  for (const sourceParticipant of state.performersByActivity.get(edge.source) || []) for (const targetParticipant of state.performersByActivity.get(edge.target) || []) {
    if (sourceParticipant === targetParticipant) continue;
    const cm = state.communicationMeans.find(item => communicationMatches(item, sourceParticipant, targetParticipant));
    if (cm) return {cm, sourceParticipant, targetParticipant};
  }
  return null;
}
function communicationGeometry(cm, sourceParticipant = cm.source, targetParticipant = cm.target) {
  const sourcePort = anchor(sourceParticipant, targetParticipant), targetPort = anchor(targetParticipant, sourceParticipant); if (!sourcePort || !targetPort) return null;
  return {sourcePort, targetPort, sourcePortId: `${cm._diagramId}:${sourceParticipant}`, targetPortId: `${cm._diagramId}:${targetParticipant}`};
}
function renderCommunicationMean(cm, sourceParticipant, targetParticipant, rendered) {
  if (rendered.has(cm._diagramId)) return communicationGeometry(cm, sourceParticipant, targetParticipant);
  const g = communicationGeometry(cm, sourceParticipant, targetParticipant); if (!g) return null; rendered.add(cm._diagramId);
  const path = svg('path', {d: curve(g.sourcePort, g.targetPort), class: 'oa-diagram-edge communication-mean'}); addEdgeInteraction(path, cm._diagramId); el.edges.appendChild(path);
  addPort(g.sourcePortId, sourceParticipant, g.sourcePort.x, g.sourcePort.y); addPort(g.targetPortId, targetParticipant, g.targetPort.x, g.targetPort.y);
  const label = svg('text', {x: (g.sourcePort.x + g.targetPort.x) / 2, y: (g.sourcePort.y + g.targetPort.y) / 2 - 11, class: 'oa-diagram-edge-label communication-label'});
  label.textContent = clean(cm.name) || 'Communication mean'; addEdgeInteraction(label, cm._diagramId); el.edges.appendChild(label); return g;
}
function renderExchangeThroughCommunication(edge, id, match, rendered) {
  const g = renderCommunicationMean(match.cm, match.sourceParticipant, match.targetParticipant, rendered); if (!g) return false;
  const a = anchorToPoint(edge.source, g.sourcePort), b = anchorToPoint(edge.target, g.targetPort); if (!a || !b) return false;
  const first = svg('path', {d: curve(a, g.sourcePort), class: 'oa-diagram-edge operational-exchange exchange-access', 'marker-end': 'url(#oaInteractionArrow)'});
  const second = svg('path', {d: curve(g.targetPort, b), class: 'oa-diagram-edge operational-exchange exchange-access', 'marker-end': 'url(#oaInteractionArrow)'});
  addEdgeInteraction(first, id); addEdgeInteraction(second, id); el.edges.appendChild(first); el.edges.appendChild(second);
  const label = svg('text', {x: (a.x + g.sourcePort.x) / 2, y: (a.y + g.sourcePort.y) / 2 - 8, class: 'oa-diagram-edge-label interaction-label'});
  label.textContent = clean(edge.name) || 'Interaction'; addEdgeInteraction(label, id); el.edges.appendChild(label); return true;
}
function renderDirectExchange(edge, id) { const a = anchor(edge.source, edge.target), b = anchor(edge.target, edge.source); if (!a || !b) return;
  const path = svg('path', {d: curve(a, b), class: 'oa-diagram-edge operational-exchange', 'marker-end': 'url(#oaInteractionArrow)'}); addEdgeInteraction(path, id); el.edges.appendChild(path);
  const label = svg('text', {x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 - 8, class: 'oa-diagram-edge-label interaction-label'}); label.textContent = clean(edge.name) || 'Interaction'; addEdgeInteraction(label, id); el.edges.appendChild(label); }
function renderOrdinary(edge, id) {
  if (['CONTAINS', 'PERFORMS', 'LOCATED_IN', 'COMMUNICATION_MEAN', 'OPERATIONAL_EXCHANGE'].includes(edge.type)) return;
  if (!state.showCapabilities && (edge.type === 'SUPPORTS_CAPABILITY' || state.byId.get(edge.source)?.type === 'OperationalCapability' || state.byId.get(edge.target)?.type === 'OperationalCapability')) return;
  if (!isVisibleNode(state.byId.get(edge.source)) || !isVisibleNode(state.byId.get(edge.target))) return;
  const a = anchor(edge.source, edge.target), b = anchor(edge.target, edge.source); if (!a || !b) return;
  const cls = edge.type === 'SUPPORTS_CAPABILITY' ? 'supports-capability' : 'ordinary-relation';
  const path = svg('path', {d: curve(a, b), class: `oa-diagram-edge ${cls}`, 'marker-end': 'url(#oaRelationArrow)'}); addEdgeInteraction(path, id); el.edges.appendChild(path);
  const label = svg('text', {x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 - 7, class: 'oa-diagram-edge-label relation-label'}); label.textContent = clean(edge.name) || clean(edge.type).toLowerCase().replaceAll('_', ' '); addEdgeInteraction(label, id); el.edges.appendChild(label);
}

export function renderEdges() {
  if (!state.ready) return;
  el.edges.innerHTML = `<defs><marker id="oaInteractionArrow" markerWidth="9" markerHeight="9" refX="8" refY="4.5" orient="auto"><path d="M0,0 L9,4.5 L0,9 z" class="oa-interaction-arrow-head"></path></marker>
    <marker id="oaRelationArrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 z" class="oa-relation-arrow-head"></path></marker></defs>`;
  el.ports.innerHTML = ''; const rendered = new Set(), edges = state.model.edges || [];
  edges.forEach((edge, i) => { if (edge.type !== 'OPERATIONAL_EXCHANGE') return; const id = edgeId(edge, i), match = communicationForExchange(edge);
    if (!match || !renderExchangeThroughCommunication(edge, id, match, rendered)) renderDirectExchange(edge, id); });
  state.communicationMeans.forEach(cm => { if (!rendered.has(cm._diagramId) && isVisibleNode(state.byId.get(cm.source)) && isVisibleNode(state.byId.get(cm.target))) renderCommunicationMean(cm, cm.source, cm.target, rendered); });
  edges.forEach((edge, i) => renderOrdinary(edge, edgeId(edge, i))); updateSelection();
}

export function render() {
  const hasNodes = [...state.byId.values()].some(isVisibleNode); el.empty.hidden = hasNodes; el.scene.hidden = !hasNodes;
  if (!hasNodes) { state.selected.clear(); updateSelection(); return; }
  expandAllContainers(); updateBounds(); renderNodes(); renderEdges(); applyView();
}
