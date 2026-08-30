import {PARTICIPANTS, state, minFor, buildModel, autoLayout, loadSaved, persist, descendants,
  minimumContainerDimensions, visibleLayoutEntries, storageKey, signatureForModel,
  PAD, HEADER, depth} from './oa_diagram_v2_state.js';
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

function updateNode(id) {
  const p = state.layout.get(id), node = el.nodes.querySelector(`[data-node-id="${CSS.escape(id)}"]`); if (!p || !node) return;
  Object.assign(node.style, {left: `${p.x}px`, top: `${p.y}px`, width: `${p.w}px`, height: `${p.h}px`});
}
function updateAllNodes() { state.layout.forEach((_value, id) => updateNode(id)); }

function expandContainerAroundChildren(id) {
  const box = state.layout.get(id);
  if (!box || !PARTICIPANTS.has(state.byId.get(id)?.type)) return;
  const children = (state.children.get(id) || []).map(child => state.layout.get(child)).filter(Boolean);
  if (!children.length) return;

  const previousRight = box.x + box.w;
  const previousBottom = box.y + box.h;
  const minChildX = Math.min(...children.map(child => child.x));
  const minChildY = Math.min(...children.map(child => child.y));
  const maxChildX = Math.max(...children.map(child => child.x + child.w));
  const maxChildY = Math.max(...children.map(child => child.y + child.h));
  const [minW, minH] = minFor(state.byId.get(id)?.type);

  const left = Math.min(box.x, minChildX - PAD);
  const top = Math.min(box.y, minChildY - HEADER - PAD);
  const right = Math.max(previousRight, maxChildX + PAD, left + minW);
  const bottom = Math.max(previousBottom, maxChildY + PAD, top + minH);

  box.x = left;
  box.y = top;
  box.w = right - left;
  box.h = bottom - top;
}

function expandAncestorsAround(id) {
  let current = state.parent.get(id);
  const seen = new Set();
  while (current && !seen.has(current)) {
    seen.add(current);
    expandContainerAroundChildren(current);
    current = state.parent.get(current);
  }
}

function normalizeContainersAllDirections() {
  [...state.byId.values()]
    .filter(node => PARTICIPANTS.has(node.type))
    .sort((a, b) => depth(b.id) - depth(a.id))
    .forEach(node => expandContainerAroundChildren(node.id));
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
  if (!allowInsideContainer && event.target.closest('.oa-diagram-node, .oa-diagram-port, .oa-diagram-edge, .oa-diagram-edge-label')) return;
  if (event.target.closest('.oa-diagram-port, .oa-diagram-edge, .oa-diagram-edge-label, .oa-diagram-resize-handle')) return;
  event.stopImmediatePropagation(); event.preventDefault();
  state.drag = {kind: 'pan', pointerId: event.pointerId, x: event.clientX, y: event.clientY, vx: state.view.x, vy: state.view.y, moved: false};
  el.viewport.setPointerCapture?.(event.pointerId); el.viewport.classList.add('is-panning');
}

function zoomSelectionPoint(event) {
  const rect = el.viewport.getBoundingClientRect();
  return {
    x: event.clientX - rect.left + el.viewport.scrollLeft,
    y: event.clientY - rect.top + el.viewport.scrollTop,
  };
}

function updateZoomSelectionVisual(d, current) {
  const left = Math.min(d.startContentX, current.x);
  const top = Math.min(d.startContentY, current.y);
  const width = Math.abs(current.x - d.startContentX);
  const height = Math.abs(current.y - d.startContentY);
  d.selection = {left, top, width, height};
  if (!el.zoomRect) return;
  Object.assign(el.zoomRect.style, {left: `${left}px`, top: `${top}px`, width: `${width}px`, height: `${height}px`});
}

function beginZoomSelection(event) {
  if (event.button !== 2) return false;
  event.stopImmediatePropagation(); event.preventDefault();
  const start = zoomSelectionPoint(event);
  state.drag = {
    kind: 'zoom-selection', pointerId: event.pointerId,
    x: event.clientX, y: event.clientY, moved: false,
    startContentX: start.x, startContentY: start.y,
    selection: {left: start.x, top: start.y, width: 0, height: 0},
  };
  el.viewport.setPointerCapture?.(event.pointerId);
  el.viewport.classList.add('is-zoom-selecting');
  if (el.zoomRect) {
    el.zoomRect.hidden = false;
    Object.assign(el.zoomRect.style, {left: `${start.x}px`, top: `${start.y}px`, width: '0px', height: '0px'});
  }
  return true;
}

function zoomToSelection(selection) {
  if (!selection || selection.width < 12 || selection.height < 12) return;
  const viewportWidth = el.viewport.clientWidth, viewportHeight = el.viewport.clientHeight;
  if (!viewportWidth || !viewportHeight) return;

  const oldZoom = state.view.zoom;
  const modelLeft = (selection.left - state.view.x) / oldZoom;
  const modelTop = (selection.top - state.view.y) / oldZoom;
  const modelWidth = selection.width / oldZoom;
  const modelHeight = selection.height / oldZoom;
  const modelCenterX = modelLeft + modelWidth / 2;
  const modelCenterY = modelTop + modelHeight / 2;
  const pad = 28;
  const next = Math.max(.25, Math.min(2.5,
    (viewportWidth - pad * 2) / Math.max(1, modelWidth),
    (viewportHeight - pad * 2) / Math.max(1, modelHeight)));

  el.viewport.scrollLeft = 0;
  el.viewport.scrollTop = 0;
  state.view.zoom = next;
  state.view.x = viewportWidth / 2 - modelCenterX * next;
  state.view.y = viewportHeight / 2 - modelCenterY * next;
  applyView(); persist();
}

function participantHeaderUnderPointer(event) {
  for (const item of document.elementsFromPoint(event.clientX, event.clientY)) {
    const header = item.closest?.('.oa-diagram-node-header');
    const node = header?.closest('.oa-diagram-node');
    if (node?.dataset.nodeId && PARTICIPANTS.has(node.dataset.nodeType)) return node;
  }
  return null;
}

function onPointerDownCapture(event) {
  if (beginZoomSelection(event)) return;

  if (event.button === 0 && event.target.closest('.oa-diagram-edge, .oa-diagram-edge-label')) {
    const underlyingParticipant = participantHeaderUnderPointer(event);
    if (underlyingParticipant) { beginMove(event, underlyingParticipant.dataset.nodeId); return; }
  }

  const resize = event.target.closest('.oa-diagram-resize-handle');
  if (resize) { const node = resize.closest('.oa-diagram-node'); if (node?.dataset.nodeId) beginResize(event, node.dataset.nodeId); return; }

  const node = event.target.closest('.oa-diagram-node');
  if (node?.dataset.nodeId) {
    const isParticipant = PARTICIPANTS.has(node.dataset.nodeType);
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

  if (d.kind === 'zoom-selection') {
    updateZoomSelectionVisual(d, zoomSelectionPoint(event));
    return;
  }
  if (d.kind === 'pan') { state.view.x = d.vx + px; state.view.y = d.vy + py; applyView(); return; }
  const dx = px / state.view.zoom, dy = py / state.view.zoom;

  if (d.kind === 'move') {
    d.ids.forEach(id => {
      const p = state.layout.get(id), start = d.startPositions.get(id);
      if (p && start) { p.x = start.x + dx; p.y = start.y + dy; }
    });
    expandAncestorsAround(d.id); updateAllNodes(); updateBounds(); scheduleEdgeRender(); return;
  }

  if (d.kind === 'resize') {
    const p = state.layout.get(d.id); if (!p) return;
    const [minW, minH] = PARTICIPANTS.has(state.byId.get(d.id)?.type) ? minimumContainerDimensions(d.id) : minFor(state.byId.get(d.id)?.type);
    p.w = Math.max(minW, d.w + dx); p.h = Math.max(minH, d.h + dy);
    expandAncestorsAround(d.id); updateAllNodes(); updateBounds(); scheduleEdgeRender();
  }
}

function onPointerEndCapture(event) {
  const d = state.drag; if (!d || d.pointerId !== event.pointerId) return;
  event.stopImmediatePropagation();
  if (d.moved) state.suppressClickUntil = Date.now() + 160;

  if (d.kind === 'zoom-selection') {
    if (el.zoomRect) el.zoomRect.hidden = true;
    el.viewport.classList.remove('is-zoom-selecting');
    state.drag = null;
    if (d.moved) zoomToSelection(d.selection);
    return;
  }

  el.nodes.querySelectorAll('.is-dragging').forEach(node => node.classList.remove('is-dragging'));
  state.drag = null; el.viewport.classList.remove('is-panning', 'is-dragging');
  if (edgeRenderFrame) { cancelAnimationFrame(edgeRenderFrame); edgeRenderFrame = 0; }
  normalizeContainersAllDirections(); updateAllNodes(); updateBounds(); renderEdges(); persist();
}

function zoom(factor, clientX = null, clientY = null) {
  const rect = el.viewport.getBoundingClientRect(), old = state.view.zoom, next = Math.max(.25, Math.min(2.5, old * factor));
  const px = clientX == null ? rect.width / 2 : clientX - rect.left + el.viewport.scrollLeft;
  const py = clientY == null ? rect.height / 2 : clientY - rect.top + el.viewport.scrollTop;
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
  el.viewport.scrollLeft = 0; el.viewport.scrollTop = 0;
  state.view = {x: (rect.width - w * z) / 2 - minX * z, y: (rect.height - h * z) / 2 - minY * z, zoom: z}; applyView();
  if (persistView) persist();
}

function resetLayout() {
  try { localStorage.removeItem(storageKey()); } catch (_error) {}
  const keepCapabilities = state.showCapabilities;
  state.view = {x: 28, y: 28, zoom: 1}; autoLayout(); state.showCapabilities = keepCapabilities;
  el.viewport.scrollLeft = 0; el.viewport.scrollTop = 0;
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

function installAdvancedControls() {
  const tools = document.querySelector('.oa-diagram-tools');
  if (tools && !document.getElementById('oaDiagramFullscreen')) {
    const fullscreen = document.createElement('button');
    fullscreen.id = 'oaDiagramFullscreen'; fullscreen.className = 'oa-diagram-tool'; fullscreen.type = 'button';
    fullscreen.textContent = 'Full screen'; fullscreen.setAttribute('aria-pressed', 'false');
    tools.appendChild(fullscreen); el.fullscreen = fullscreen;
  } else {
    el.fullscreen = document.getElementById('oaDiagramFullscreen');
  }

  if (!document.getElementById('oaDiagramZoomRect')) {
    const zoomRect = document.createElement('div'); zoomRect.id = 'oaDiagramZoomRect'; zoomRect.className = 'oa-diagram-zoom-rect'; zoomRect.hidden = true;
    el.viewport.appendChild(zoomRect); el.zoomRect = zoomRect;
  } else {
    el.zoomRect = document.getElementById('oaDiagramZoomRect');
  }
}

function fullscreenActive() {
  return document.fullscreenElement === el.tab || el.tab?.classList.contains('oa-diagram-fullscreen-fallback');
}

function updateFullscreenButton() {
  if (!el.fullscreen) return;
  const active = fullscreenActive();
  el.fullscreen.textContent = active ? 'Exit full screen' : 'Full screen';
  el.fullscreen.setAttribute('aria-pressed', active ? 'true' : 'false');
}

async function toggleFullscreen() {
  if (!el.tab) return;
  if (document.fullscreenElement === el.tab) {
    await document.exitFullscreen?.();
  } else if (el.tab.classList.contains('oa-diagram-fullscreen-fallback')) {
    el.tab.classList.remove('oa-diagram-fullscreen-fallback');
  } else if (el.tab.requestFullscreen) {
    try { await el.tab.requestFullscreen(); }
    catch (_error) { el.tab.classList.add('oa-diagram-fullscreen-fallback'); }
  } else {
    el.tab.classList.add('oa-diagram-fullscreen-fallback');
  }
  updateFullscreenButton();
  requestAnimationFrame(() => { updateBounds(); fitView(false); });
}

function publishDiagramModel(model) {
  window.dispatchEvent(new CustomEvent('oa:diagram-model-rendered', {
    detail: {model: model || {nodes: [], drafts: [], edges: []}, session: state.session}
  }));
}

function setModel(model, session) {
  const nextModel = model || {nodes: [], drafts: [], edges: []};
  const nextSession = String(session || '').trim() || 'default';
  const nextSignature = signatureForModel(nextModel);
  const sessionChanged = nextSession !== state.session;

  if (!sessionChanged && state.modelSignature === nextSignature) {
    state.model = nextModel;
    publishDiagramModel(nextModel);
    return;
  }

  if (sessionChanged) {
    state.session = nextSession; state.view = {x: 28, y: 28, zoom: 1}; state.selected.clear(); state.modelSignature = '';
    const saved = loadSaved(); state.showCapabilities = typeof saved.showCapabilities === 'boolean' ? saved.showCapabilities : false; updateCapabilityButton();
  }
  state.model = nextModel; state.modelSignature = nextSignature; buildModel(state.model); autoLayout(); render(); persist();
  publishDiagramModel(nextModel);
}

function init() {
  if (state.ready) return;
  installMarkup(); if (!bindElements()) return; state.ready = true;
  installAdvancedControls();
  const saved = loadSaved(); if (typeof saved.showCapabilities === 'boolean') state.showCapabilities = saved.showCapabilities; updateCapabilityButton();

  el.viewport.addEventListener('contextmenu', event => event.preventDefault());
  el.viewport.addEventListener('pointerdown', onPointerDownCapture, {capture: true});
  el.viewport.addEventListener('pointermove', onPointerMoveCapture, {capture: true});
  el.viewport.addEventListener('pointerup', onPointerEndCapture, {capture: true});
  el.viewport.addEventListener('pointercancel', onPointerEndCapture, {capture: true});
  el.viewport.addEventListener('wheel', event => {
    if (!(event.ctrlKey || event.metaKey)) return;
    event.preventDefault(); zoom(event.deltaY < 0 ? 1.12 : .89, event.clientX, event.clientY);
  }, {passive: false});

  document.getElementById('oaDiagramZoomIn')?.addEventListener('click', () => zoom(1.2));
  document.getElementById('oaDiagramZoomOut')?.addEventListener('click', () => zoom(.82));
  document.getElementById('oaDiagramFit')?.addEventListener('click', () => fitView());
  document.getElementById('oaDiagramReset')?.addEventListener('click', resetLayout);
  el.capabilities?.addEventListener('click', toggleCapabilities);
  el.fullscreen?.addEventListener('click', toggleFullscreen);
  document.addEventListener('fullscreenchange', () => {
    updateFullscreenButton(); requestAnimationFrame(() => { updateBounds(); fitView(false); });
  });
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && el.tab?.classList.contains('oa-diagram-fullscreen-fallback')) {
      el.tab.classList.remove('oa-diagram-fullscreen-fallback'); updateFullscreenButton(); requestAnimationFrame(() => fitView(false));
    }
  });

  document.querySelector('[data-tab="diagram"]')?.addEventListener('click', () => requestAnimationFrame(() => { renderEdges(); if (!loadSaved().view) fitView(false); }));
  if (typeof window.applyState === 'function') {
    const priorApplyState = window.applyState;
    window.applyState = function applyStateWithOperationalDiagramV4(nextState) {
      priorApplyState(nextState); setModel(nextState?.model || {}, nextState?.session_id || state.session);
    };
  }
  window.oaDiagram = Object.freeze({setMode, getSelection: selectionPayload,
    getView() { return {...state.view}; },
    clearSelection() { state.selected.clear(); updateSelection(); }, fitView, resetLayout, toggleFullscreen,
    setCapabilitiesVisible(value) { state.showCapabilities = !!value; updateCapabilityButton(); render(); fitView(); persist(); },
    render(model, session = state.session) { setModel(model, session); }});
}

init();
