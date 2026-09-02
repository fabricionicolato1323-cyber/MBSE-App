import {state, persist} from './oa_diagram_v2_state.js';
import {
  el,
  applyView,
  getCanvasOrigin,
  renderEdges,
  setPortVerticalRatio,
  persistPortOffsets,
  resetPortOffsets,
} from './oa_diagram_v2_render.js';

let drag = null;
let renderFrame = 0;
let viewFrame = 0;
let forceOriginScroll = false;
let edgeObserver = null;
let scenarioAuthoringObserver = null;

function scenarioAuthoringActive() {
  const bar = document.getElementById('oaScenarioAuthoringBar');
  return state.mode === 'scenario' && Boolean(bar && !bar.hidden);
}

function syncScenarioAuthoringClass() {
  el.tab?.classList.toggle('oa-scenario-authoring-active', scenarioAuthoringActive());
}

function blockScenarioAuthoringManipulation(event) {
  if (event.button !== 0 || !scenarioAuthoringActive()) return;
  if (!el.viewport?.contains(event.target)) return;

  // During Operational Scenario authoring the left button belongs exclusively
  // to path selection. Stop the normal diagram pointer-down pipeline before it
  // can start move, resize, pan or port-drag gestures. Do not preventDefault():
  // the browser must still synthesize the click consumed by oa_scenario.js.
  event.stopPropagation();
  event.stopImmediatePropagation();
}

function installScenarioAuthoringSelectionGuard() {
  if (!el.tab || el.tab.dataset.scenarioSelectionGuardInstalled === 'true') return;
  el.tab.dataset.scenarioSelectionGuardInstalled = 'true';

  window.addEventListener('pointerdown', blockScenarioAuthoringManipulation, {capture: true});

  scenarioAuthoringObserver?.disconnect();
  scenarioAuthoringObserver = new MutationObserver(syncScenarioAuthoringClass);
  scenarioAuthoringObserver.observe(el.tab, {
    childList: true,
    subtree: true,
    attributes: true,
    attributeFilter: ['hidden'],
  });

  if (!document.getElementById('oaScenarioSelectionCursorStyle')) {
    const style = document.createElement('style');
    style.id = 'oaScenarioSelectionCursorStyle';
    style.textContent = `
      #diagramTab.oa-scenario-authoring-active .oa-diagram-viewport {
        cursor: crosshair !important;
      }
      #diagramTab.oa-scenario-authoring-active .oa-diagram-node {
        cursor: not-allowed !important;
      }
      #diagramTab.oa-scenario-authoring-active .oa-diagram-node.type-operationalactivity,
      #diagramTab.oa-scenario-authoring-active .oa-diagram-edge.operational-exchange,
      #diagramTab.oa-scenario-authoring-active .oa-diagram-edge-label.interaction-label {
        cursor: crosshair !important;
      }
      #diagramTab.oa-scenario-authoring-active .oa-diagram-resize-handle {
        pointer-events: none !important;
        opacity: .18 !important;
        cursor: not-allowed !important;
      }
      #diagramTab.oa-scenario-authoring-active .oa-diagram-port {
        cursor: not-allowed !important;
      }
    `;
    document.head.appendChild(style);
  }

  syncScenarioAuthoringClass();
}

function ensureRoutedSourceArrows() {
  document.querySelectorAll('#oaDiagramEdges .source-segment').forEach(path => {
    path.setAttribute('marker-end', 'url(#oaInteractionArrow)');
  });
}

function normalizeScrollableView() {
  viewFrame = 0;
  if (!el.viewport) return;

  const origin = getCanvasOrigin();
  const zoom = Math.max(0.0001, Number(state.view.zoom) || 1);

  // Fit is calculated in semantic/model coordinates. The renderer adds a
  // presentation-only origin so negative model coordinates live in real DOM
  // space. Scrolling by that origin cancels the presentation offset, preserving
  // the established Fit behaviour while leaving a genuine reserve to its left.
  if (forceOriginScroll) {
    el.viewport.scrollLeft = Math.max(0, origin.x * zoom);
    el.viewport.scrollTop = Math.max(0, origin.y * zoom);
    forceOriginScroll = false;
  }

  let changed = false;
  const viewX = Number(state.view.x) || 0;
  const viewY = Number(state.view.y) || 0;

  // CSS translation can move content before the native scrollbar's zero point.
  // Convert any negative translation into an equivalent positive scroll offset.
  // The picture stays in the same place, but the user can now drag the scrollbar
  // back toward zero to reveal the complete left/top side of the diagram.
  if (viewX < 0) {
    el.viewport.scrollLeft = Math.max(0, el.viewport.scrollLeft - viewX);
    state.view.x = 0;
    changed = true;
  }
  if (viewY < 0) {
    el.viewport.scrollTop = Math.max(0, el.viewport.scrollTop - viewY);
    state.view.y = 0;
    changed = true;
  }

  if (changed) {
    applyView();
    persist();
  }
}

function scheduleViewNormalization(forceOrigin = false) {
  forceOriginScroll ||= forceOrigin;
  if (viewFrame) return;
  // Some toolbar actions themselves defer layout work with requestAnimationFrame.
  // Two frames guarantee that the conversion runs after their final view update.
  viewFrame = requestAnimationFrame(() => {
    viewFrame = requestAnimationFrame(normalizeScrollableView);
  });
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
  const origin = getCanvasOrigin();
  return (contentY - state.view.y) / Math.max(0.0001, state.view.zoom) - origin.y;
}

function ratioForPointer(event, participantId) {
  const box = state.layout.get(participantId);
  if (!box) return null;
  const margin = Math.min(18, Math.max(10, box.h * 0.06));
  const usable = Math.max(1, box.h - margin * 2);
  return Math.max(0, Math.min(1, (modelYForPointer(event) - box.y - margin) / usable));
}

function beginPortDrag(event) {
  if (event.button !== 0 || scenarioAuthoringActive()) return;
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

  installScenarioAuthoringSelectionGuard();

  el.viewport.addEventListener('pointerdown', beginPortDrag, {capture: true});
  el.viewport.addEventListener('pointermove', movePort, {capture: true});
  el.viewport.addEventListener('pointerup', endPortDrag, {capture: true});
  el.viewport.addEventListener('pointercancel', endPortDrag, {capture: true});
  el.viewport.addEventListener('wheel', () => scheduleViewNormalization(false), {capture: true, passive: true});

  document.getElementById('oaDiagramReset')?.addEventListener('click', () => {
    resetPortOffsets();
    scheduleViewNormalization(false);
  }, {capture: true});
  document.getElementById('oaDiagramFit')?.addEventListener('click', () => scheduleViewNormalization(true), {capture: true});
  document.getElementById('oaDiagramZoomIn')?.addEventListener('click', () => scheduleViewNormalization(false), {capture: true});
  document.getElementById('oaDiagramZoomOut')?.addEventListener('click', () => scheduleViewNormalization(false), {capture: true});

  // Window capture runs before the diagram's own pointer-up handlers. The
  // deferred normalization therefore sees the final drag/pan/area-zoom state.
  window.addEventListener('pointerup', () => scheduleViewNormalization(false), {capture: true});
  window.addEventListener('pointercancel', () => scheduleViewNormalization(false), {capture: true});
  window.addEventListener('oa:diagram-model-rendered', () => scheduleViewNormalization(false));

  // Node moves, resizing and model polling rebuild the SVG connection layer.
  // Re-assert the source-segment marker after every such redraw so Activity -> P
  // direction never disappears after an unrelated diagram gesture.
  edgeObserver?.disconnect();
  if (el.edges) {
    edgeObserver = new MutationObserver(() => requestAnimationFrame(ensureRoutedSourceArrows));
    edgeObserver.observe(el.edges, {childList: true, subtree: true});
  }

  scheduleRender();
  scheduleViewNormalization(false);
}

if (el.viewport) install();
else requestAnimationFrame(install);
