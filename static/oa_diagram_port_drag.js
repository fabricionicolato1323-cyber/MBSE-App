import {state} from './oa_diagram_v2_state.js';
import {
  el,
  renderEdges,
  setPortVerticalRatio,
  persistPortOffsets,
  resetPortOffsets,
} from './oa_diagram_v2_render.js';

let drag = null;
let renderFrame = 0;

function scheduleRender() {
  if (renderFrame) return;
  renderFrame = requestAnimationFrame(() => {
    renderFrame = 0;
    renderEdges();
    // The routed exchange enters the communication mean at the source port.
    // Keep the directional marker on that access segment as well as the target.
    document.querySelectorAll('#oaDiagramEdges .source-segment').forEach(path => {
      path.setAttribute('marker-end', 'url(#oaInteractionArrow)');
    });
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
  document.querySelectorAll('#oaDiagramEdges .source-segment').forEach(path => {
    path.setAttribute('marker-end', 'url(#oaInteractionArrow)');
  });
}

function install() {
  if (!el.viewport || el.viewport.dataset.portDragInstalled === 'true') return;
  el.viewport.dataset.portDragInstalled = 'true';

  // Capture after the main v4 interaction layer. The base layer deliberately
  // ignores pointer gestures that start on a port, so this handler owns them.
  el.viewport.addEventListener('pointerdown', beginPortDrag, {capture: true});
  el.viewport.addEventListener('pointermove', movePort, {capture: true});
  el.viewport.addEventListener('pointerup', endPortDrag, {capture: true});
  el.viewport.addEventListener('pointercancel', endPortDrag, {capture: true});

  // Reset layout must also return ports to their centered positions. Capture
  // runs before the existing Reset layout click handler performs its render.
  document.getElementById('oaDiagramReset')?.addEventListener('click', () => {
    resetPortOffsets();
  }, {capture: true});

  scheduleRender();
}

if (el.viewport) install();
else requestAnimationFrame(install);
