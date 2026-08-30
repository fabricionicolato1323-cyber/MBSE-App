import {state, visibleLayoutEntries, persist} from './oa_diagram_v2_state.js';
import {
  el,
  updateBounds,
  applyView,
  getCanvasOrigin,
  renderEdges,
} from './oa_diagram_v2_render.js';

const query = new URLSearchParams(window.location.search);
const detachedUtilityWindow = query.get('detachedPanel') === 'utility';
let firstDetachedDiagramFitDone = false;
let scheduledFitFrame = 0;

function correctedFitView({persistView = true} = {}) {
  if (!el.viewport) return false;
  const entries = visibleLayoutEntries();
  if (!entries.length) return false;

  // updateBounds may change the presentation-only canvas origin when model
  // elements have negative coordinates. Fit must use the origin actually used
  // by the renderer, otherwise the camera is centered in a different coordinate
  // system and can appear to behave like Reset layout.
  updateBounds();
  const origin = getCanvasOrigin();
  const viewportWidth = el.viewport.clientWidth;
  const viewportHeight = el.viewport.clientHeight;
  if (!viewportWidth || !viewportHeight) return false;

  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;
  entries.forEach(([, box]) => {
    minX = Math.min(minX, box.x + origin.x);
    minY = Math.min(minY, box.y + origin.y);
    maxX = Math.max(maxX, box.x + box.w + origin.x);
    maxY = Math.max(maxY, box.y + box.h + origin.y);
  });

  const modelWidth = Math.max(1, maxX - minX);
  const modelHeight = Math.max(1, maxY - minY);
  const pad = 38;
  const zoom = Math.max(
    .25,
    Math.min(
      1.25,
      Math.max(1, viewportWidth - pad * 2) / modelWidth,
      Math.max(1, viewportHeight - pad * 2) / modelHeight,
    ),
  );

  el.viewport.scrollLeft = 0;
  el.viewport.scrollTop = 0;
  state.view = {
    x: (viewportWidth - modelWidth * zoom) / 2 - minX * zoom,
    y: (viewportHeight - modelHeight * zoom) / 2 - minY * zoom,
    zoom,
  };
  applyView();
  renderEdges();

  // A detached browser window has a different viewport from the docked panel.
  // Do not overwrite the docked camera merely because the user fitted the
  // detached view. Node positions remain shared through the normal layout state.
  if (persistView && !detachedUtilityWindow) persist();
  return true;
}

function scheduleCorrectedFit(options = {}) {
  if (scheduledFitFrame) cancelAnimationFrame(scheduledFitFrame);
  scheduledFitFrame = requestAnimationFrame(() => {
    scheduledFitFrame = requestAnimationFrame(() => {
      scheduledFitFrame = 0;
      correctedFitView(options);
    });
  });
}

function diagramIsVisible() {
  return Boolean(el.tab && el.tab.classList.contains('active') && !el.tab.hidden);
}

function installFitButtonOverride() {
  const fitButton = document.getElementById('oaDiagramFit');
  if (!fitButton || fitButton.dataset.correctedFitInstalled === 'true') return;
  fitButton.dataset.correctedFitInstalled = 'true';

  // Capture phase intentionally runs before the original bubble listener.
  // Fit is camera-only: it never calls autoLayout or changes node geometry.
  fitButton.addEventListener('click', event => {
    event.preventDefault();
    event.stopImmediatePropagation();
    correctedFitView({persistView: !detachedUtilityWindow});
  }, true);
}

function installDetachedWindowFit() {
  if (!detachedUtilityWindow) return;

  const diagramTabButton = document.querySelector('[data-tab="diagram"]');
  diagramTabButton?.addEventListener('click', () => {
    if (firstDetachedDiagramFitDone) return;
    firstDetachedDiagramFitDone = true;
    scheduleCorrectedFit({persistView: false});
  });

  window.addEventListener('oa:diagram-model-rendered', () => {
    if (firstDetachedDiagramFitDone || !diagramIsVisible()) return;
    firstDetachedDiagramFitDone = true;
    scheduleCorrectedFit({persistView: false});
  });
}

function installFullscreenCorrection() {
  document.addEventListener('fullscreenchange', () => {
    if (!diagramIsVisible()) return;
    scheduleCorrectedFit({persistView: !detachedUtilityWindow});
  });
}

function install() {
  installFitButtonOverride();
  installDetachedWindowFit();
  installFullscreenCorrection();
  window.oaCorrectedDiagramFit = correctedFitView;
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', install, {once: true});
} else {
  install();
}
