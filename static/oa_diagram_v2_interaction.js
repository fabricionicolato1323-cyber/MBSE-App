import {PARTICIPANTS, state, minFor, buildModel, autoLayout, loadSaved, persist, descendants,
  expandAllContainers, minimumContainerDimensions, visibleLayoutEntries, storageKey,
  constrainChildToParent, signatureForModel} from './oa_diagram_v2_state.js';
import {el, installMarkup, bindElements, updateCapabilityButton, updateSelection, selectionPayload,
  updateBounds, applyView, renderEdges, render} from './oa_diagram_v2_render.js';

let edgeRenderFrame = 0;

function scheduleEdgeRender() {
  if (edgeRenderFrame) return;
  edgeRenderFrame = requestAnimationFrame(() => {
    edgeRenderFrame = 0;
    renderEdges();
  });
}

function focusForManipulation(id, event) {
  if (state.mode !== 'normal') return;
  if (!(event.ctrlKey || event.metaKey)) state.selected.clear();
  state.selected.add(`node:${id}`); updateSelection();
}

function beginMove(event, id) {
  if (event.button !== 0) return;
  event.stopImmediatePropagation(); event.preventDefault(); focusForManipulation(id, event);
  const ids = [id, ...descendants(id)], startPositions = new Map();
  ids.forEach(nodeId => { const p = state.layout.get(nodeId); if (p) startPositions.set(nodeId, {x: p.x, y: p.y}); });
  state.drag = {kind: 'move', id, ids, pointerId: event.pointerId, x: event.clientX, y: event.clientY, moved: false, startPositions};
  el.viewport.setPointerCapture?.(event.pointerId);
  el.nodes.querySelector(`[data-node-id="${CSS.escape(id)}"]`)?.classList.add('is-dragging');
  el.viewport.classList.add('is-dragging');
}

function beginResize(event, id) {
  if (event.button !== 0) return;
  event.stopImmediatePropagation(); event.preventDefault(); focusForManipulation(id, event);
  const p = state.layout.get(id); if (!p) return;
  state.drag = {kind: 'resize', id, pointerId: event.pointerId, x: event.clientX, y: event.clientY, w: p.w, h: p.h, moved: false};
  el.viewport.setPointerCapture?.(event.pointerId);
  el.nodes.querySelector(`[data-node-id="${CSS.escape(id)}"]`)?.classList.add('is-dragging');
  el.viewport.classList.add('is-dragging');
}

function beginPan(event, allowInsideContainer = false) {
  if (event.button !== 0) return;
  if (!allowInsideContainer && event.target.closest('.oa-diagram-node, .oa-diagram-port, .oa-diagram-edge-label')) return;
  if (event.target.closest('.oa-diagram-port, .oa-diagram-edge-label, .oa-diagram-resize-handle')) return;
  event.stopImmediatePropagation(); event.preventDefault();
  state.drag = {kind: 'pan', pointerId: event.pointerId, x: event.clientX, y: event.clientY, vx: state.view.x, vy: state.view.y, moved: false};
  el.viewport.setPointerCapture?.(event.pointerId); el.viewport.classList.add('is-panning');
}

function updateNode(id) {
  const p = state.layout.get(id), node = el.nodes.querySelector(`[data-node-id="${CSS.escape(id)}"]`); if (!p || !node) return;
  Object.assign(node.style, {left: `${p.x}px`, top: `${p.y}px`, width: `${p.w}px`, height: `${p.h}px`});
}
function updateAllNodes() { state.layout.forEach((_value, id) => updateNode(id)); }

function onPointerDownCapture(event) {
  const resize = event.target.closest('.oa-diagram-resize-handle');
  if (resize) { const node = resize.closest('.oa-diagram-node'); if (node?.dataset.nodeId) beginResize(event, node.dataset.nodeId); return; }

  const node = event.target.closest('.oa-diagram-node');
  if (node?.dataset.nodeId) {
    const isParticipant = PARTICIPANTS.has(node.dataset.nodeType);
    // Containers are moved from their header so empty container space remains
    // useful for canvas panning. Activities/capabilities remain draggable from
    // the whole block.
    if (!isParticipant || event.target.closest('.oa-diagram-node-header')) beginMove(event, node.dataset.nodeId);
    else beginPan(event, true);
    return;
  }
  beginPan(event);
}

function onPointerMoveCapture(event) {
  const d = state.drag; if (!d || d.pointerId !== event.pointerId) return;
  event.stopImmediatePropagation(); event.preventDefault();
  const px = event.clientX - d.x, py = event.clientY - d.y; d.moved ||= Math.abs(px) + Math.abs(py) > 3;
  if (d.kind === 'pan') { state.view.x = d.vx + px; state.view.y = d.vy + py; applyView(); return; }
  const dx = px / state.view.zoom, dy = py / state.view.zoom;

  if (d.kind === 'move') {
    d.ids.forEach(id => {
      const p = state.layout.get(id), start = d.startPositions.get(id);
      if (p && start) { p.x = start.x + dx; p.y = start.y + dy; }
    });
    constrainChildToParent(d.id); expandAllContainers(); updateAllNodes(); updateBounds(); scheduleEdgeRender(); return;
  }

  if (d.kind === 'resize') {
    const p = state.layout.get(d.id); if (!p) return;
    const [minW, minH] = PARTICIPANTS.has(state.byId.get(d.id)?.type) ? minimumContainerDimensions(d.id) : minFor(state.byId.get(d.id)?.type);
    p.w = Math.max(minW, d.w + dx); p.h = Math.max(minH, d.h + dy);
    constrainChildToParent(d.id); expandAllContainers(); updateAllNodes(); updateBounds(); scheduleEdgeRender();
  }
}

function onPointerEndCapture(event) {
  const d = state.drag; if (!d || d.pointerId !== event.pointerId) return;
  event.stopImmediatePropagation();
  if (d.moved) state.suppressClickUntil = Date.now() + 160;
  el.nodes.querySelectorAll('.is-dragging').forEach(node => node.classList.remove('is-dragging'));
  state.drag = null; el.viewport.classList.remove('is-panning', 'is-dragging');
  if (edgeRenderFrame) { cancelAnimationFrame(edgeRenderFrame); edgeRenderFrame = 0; }
  expandAllContainers(); updateAllNodes(); updateBounds(); renderEdges(); persist();
}

function zoom(factor, clientX = null, clientY = null) {
  const rect = el.viewport.getBoundingClientRect(), old = state.view.zoom, next = Math.max(.25, Math.min(2.5, old * factor));
  const px = clientX == null ? rect.width / 2 : clientX - rect.left, py = clientY == null ? rect.height / 2 : clientY - rect.top;
  const sx = (px - state.view.x) / old, sy = (py - state.view.y) / old;
  state.view.zoom = next; state.view.x = px - sx * next; state.view.y = py - sy * next; applyView(); persist();
}

function fitView(persistView = true) {
  const entries = visibleLayoutEntries(); if (!entries.length) return;
  const rect = el.viewport.getBoundingClientRect(); if (!rect.width || !rect.height) return;
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  entries.forEach(([, p]) => { minX = Math.min(minX, p.x); minY = Math.min(minY, p.y); maxX = Math.max(maxX, p.x + p.w); maxY = Math.max(maxY, p.y + p.h); });
  const w = Math.max(1, maxX - minX), h = Math.max(1, maxY - minY), pad = 38;
  const z = Math.max(.25, Math.min(1.25, (rect.width - pad * 2) / w, (rect.height - pad * 2) / h));
  state.view = {x: (rect.width - w * z) / 2 - minX * z, y: (rect.height - h * z) / 2 - minY * z, zoom: z}; applyView();
  if (persistView) persist();
}

function resetLayout() {
  try { localStorage.removeItem(storageKey()); } catch (_error) {}
  const keepCapabilities = state.showCapabilities;
  state.view = {x: 28, y: 28, zoom: 1}; autoLayout(); state.showCapabilities = keepCapabilities;
  render(); persist(); requestAnimationFrame(() => fitView());
}

function toggleCapabilities() {
  state.showCapabilities = !state.showCapabilities; updateCapabilityButton();
  state.selected = new Set([...state.selected].filter(key => !key.startsWith('node:') || state.byId.get(key.slice(5))?.type !== 'OperationalCapability'));
  render(); fitView(); persist();
}

function setMode(mode) {
  state.mode = mode === 'scenario' ? 'scenario' : 'normal'; state.selected.clear();
  if (el.mode) el.mode.textContent = state.mode === 'scenario' ? 'Scenario selection' : 'Normal selection';
  el.tab?.classList.toggle('scenario-mode', state.mode === 'scenario'); updateSelection();
}

function setModel(model, session) {
  const nextModel = model || {nodes: [], drafts: [], edges: []};
  const nextSession = String(session || '').trim() || 'default';
  const nextSignature = signatureForModel(nextModel);
  const sessionChanged = nextSession !== state.session;

  // The web UI polls /api/state. Re-running autoLayout for an unchanged model
  // fought pointer movement and made blocks feel as if they snapped back.
  if (!sessionChanged && state.modelSignature === nextSignature) {
    state.model = nextModel;
    return;
  }

  if (sessionChanged) {
    state.session = nextSession; state.view = {x: 28, y: 28, zoom: 1}; state.selected.clear(); state.modelSignature = '';
    const saved = loadSaved(); state.showCapabilities = typeof saved.showCapabilities === 'boolean' ? saved.showCapabilities : true; updateCapabilityButton();
  }
  state.model = nextModel; state.modelSignature = nextSignature; buildModel(state.model); autoLayout(); render(); persist();
}

function init() {
  if (state.ready) return;
  installMarkup(); if (!bindElements()) return; state.ready = true;
  const saved = loadSaved(); if (typeof saved.showCapabilities === 'boolean') state.showCapabilities = saved.showCapabilities; updateCapabilityButton();
  el.viewport.addEventListener('pointerdown', onPointerDownCapture, {capture: true});
  el.viewport.addEventListener('pointermove', onPointerMoveCapture, {capture: true});
  el.viewport.addEventListener('pointerup', onPointerEndCapture, {capture: true});
  el.viewport.addEventListener('pointercancel', onPointerEndCapture, {capture: true});
  el.viewport.addEventListener('wheel', event => { event.preventDefault(); zoom(event.deltaY < 0 ? 1.12 : .89, event.clientX, event.clientY); }, {passive: false});
  document.getElementById('oaDiagramZoomIn')?.addEventListener('click', () => zoom(1.2));
  document.getElementById('oaDiagramZoomOut')?.addEventListener('click', () => zoom(.82));
  document.getElementById('oaDiagramFit')?.addEventListener('click', () => fitView());
  document.getElementById('oaDiagramReset')?.addEventListener('click', resetLayout);
  el.capabilities?.addEventListener('click', toggleCapabilities);
  document.querySelector('[data-tab="diagram"]')?.addEventListener('click', () => requestAnimationFrame(() => { renderEdges(); if (!loadSaved().view) fitView(false); }));
  if (typeof window.applyState === 'function') {
    const priorApplyState = window.applyState;
    window.applyState = function applyStateWithOperationalDiagramV2(nextState) {
      priorApplyState(nextState); setModel(nextState?.model || {}, nextState?.session_id || state.session);
    };
  }
  window.oaDiagram = Object.freeze({setMode, getSelection: selectionPayload,
    clearSelection() { state.selected.clear(); updateSelection(); }, fitView, resetLayout,
    setCapabilitiesVisible(value) { state.showCapabilities = !!value; updateCapabilityButton(); render(); fitView(); persist(); },
    render(model, session = state.session) { setModel(model, session); }});
}

init();
