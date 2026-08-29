import {state, persist} from './oa_diagram_v2_state.js';
import {
  el,
  render,
  renderEdges,
  updateBounds,
  applyView,
  setPortVerticalRatio,
  persistPortOffsets,
  resetPortOffsets,
} from './oa_diagram_v2_render.js';

const SCROLL_SAFE_MARGIN = 60;
let drag = null;
let renderFrame = 0;
let originFrame = 0;
let edgeObserver = null;

function ensureRoutedSourceArrows() {
  document.querySelectorAll('#oaDiagramEdges .source-segment').forEach(path => {
    path.setAttribute('marker-end', 'url(#oaInteractionArrow)');
  });
}

function normalizeScrollableOrigin() {
  originFrame = 0;
  if (!el.viewport || !state.layout?.size) return;

  let minX = Infinity;
  let minY = Infinity;
  state.layout.forEach(box => {
    if (!box) return;
    minX = Math.min(minX, Number(box.x));
    minY = Math.min(minY, Number(box.y));
  });
  if (!Number.isFinite(minX) || !Number.isFinite(minY)) return;

  const dx = minX < SCROLL_SAFE_MARGIN ? SCROLL_SAFE_MARGIN - minX : 0;
  const dy = minY < SCROLL_SAFE_MARGIN ? SCROLL_SAFE_MARGIN - minY : 0;
  let layoutChanged = false;
  if (dx || dy) {
    state.layout.forEach(box => {
      if (!box) return;
      box.x += dx;
      box.y += dy;
    });
    layoutChanged = true;
  }

  // Native scrollbars cannot reach visual content translated before the
  // viewport's zero coordinate. Negative view translations therefore create
  // the exact situation where the scrollbar is already fully left while the
  // diagram is still cut off. Keep translation non-negative and let the
  // native scrollbar own left/right navigation.
  const oldViewX = Number(state.view.x) || 0;
  const oldViewY = Number(state.view.y) || 0;
  state.view.x = Math.max(0, oldViewX);
  state.view.y = Math.max(0, oldViewY);
  const viewChanged = state.view.x !== oldViewX || state.view.y !== oldViewY;

  if (layoutChanged) {
    render();
  } else if (viewChanged) {
    updateBounds();
    applyView();
    renderEdges();
  }

  if (layoutChanged || viewChanged) {
    persist();
    ensureRoutedSourceArrows();
  }
}

function scheduleOriginNormalization() {
  if (originFrame) return;
  originFrame = requestAnimationFrame(normalizeScrollableOrigin);
}

function scheduleRender() {
  if (renderFrame) return;
  renderFrame = requestAnimationFrame(() => {
    renderFrame = 0;
    renderEdges();
    ensureRoutedSourceArrows();
  });
}

function modelYForPointer(event) {
  const rect = el.viewport.getBoundingClientRect();
  const contentY = event.clientY - rect.top + el.viewport.scrollTop;
  return (contentY - state.view.y) / Math.max(0.0001, state.view.zoom);
}

function ratioForPointer(event, participantId) {
  const box = state.layout.get(participantId);
  if (!box) return null;
  const margin = Math.min(18, Math.max(10, box.h * 0.06));
  const usable = Math.max(1, box.h - margin * 2);
  return Math.max(0, Math.min(1, (modelYForPointer(event) - box.y - margin) / usable));
}

function beginPortDrag(event) {
  if (event.button !== 0) return;
  const port = event.target.closest('.oa-diagram-port[data-port-id][data-participant-id]');
  if (!port) return;

  const portId = port.dataset.portId;
  const participantId = port.dataset.participantId;
  if (!portId || !participantId || !state.layout.has(participantId)) return;

  event.preventDefault();
  event.stopImmediatePropagation();
  drag = {
    pointerId: event.pointerId,
    portId,
    participantId,
    startX: event.clientX,
    startY: event.clientY,
    moved: false,
  };
  port.classList.add('is-port-dragging');
  el.viewport.setPointerCapture?.(event.pointerId);
}

function movePort(event) {
  if (!drag || drag.pointerId !== event.pointerId) return;
  event.preventDefault();
  event.stopImmediatePropagation();
  drag.moved ||= Math.abs(event.clientY - drag.startY) + Math.abs(event.clientX - drag.startX) > 3;

  const ratio = ratioForPointer(event, drag.participantId);
  if (ratio == null) return;
  setPortVerticalRatio(drag.portId, ratio);
  scheduleRender();
}

function endPortDrag(event) {
  if (!drag || drag.pointerId !== event.pointerId) return;
  event.preventDefault();
  event.stopImmediatePropagation();
  if (drag.moved) state.suppressClickUntil = Date.now() + 180;
  drag = null;
  if (renderFrame) {
    cancelAnimationFrame(renderFrame);
    renderFrame = 0;
  }
  persistPortOffsets();
  renderEdges();
  ensureRoutedSourceArrows();
}

function install() {
  if (!el.viewport || el.viewport.dataset.portDragInstalled === 'true') return;
  el.viewport.dataset.portDragInstalled = 'true';
  el.viewport.dataset.scrollOriginInstalled = 'true';

  el.viewport.addEventListener('pointerdown', beginPortDrag, {capture: true});
  el.viewport.addEventListener('pointermove', movePort, {capture: true});
  el.viewport.addEventListener('pointerup', endPortDrag, {capture: true});
  el.viewport.addEventListener('pointercancel', endPortDrag, {capture: true});
  el.viewport.addEventListener('wheel', scheduleOriginNormalization, {capture: true, passive: true});

  document.getElementById('oaDiagramReset')?.addEventListener('click', () => {
    resetPortOffsets();
  }, {capture: true});

  // Window capture runs before the diagram's own pointer-up handlers. Queueing
  // one animation frame means normalization happens after node/container drag,
  // resize, pan and area-zoom logic has finished updating the layout/view.
  window.addEventListener('pointerup', scheduleOriginNormalization, {capture: true});
  window.addEventListener('pointercancel', scheduleOriginNormalization, {capture: true});
  el.tab?.addEventListener('click', scheduleOriginNormalization, {capture: true});
  window.addEventListener('oa:diagram-model-rendered', scheduleOriginNormalization);

  // Node moves, resizing and model polling rebuild the SVG connection layer.
  // Re-assert the source-segment marker after every such redraw so Activity -> P
  // direction never disappears after an unrelated diagram gesture.
  edgeObserver?.disconnect();
  if (el.edges) {
    edgeObserver = new MutationObserver(() => requestAnimationFrame(ensureRoutedSourceArrows));
    edgeObserver.observe(el.edges, {childList: true, subtree: true});
  }

  scheduleRender();
  scheduleOriginNormalization();
}

if (el.viewport) install();
else requestAnimationFrame(install);
