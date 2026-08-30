import {
  state,
  visibleLayoutEntries,
  persist,
  autoLayout,
  storageKey,
} from './oa_diagram_v2_state.js';
import {
  el,
  updateBounds,
  applyView,
  getCanvasOrigin,
  renderEdges,
  render,
  resetPortOffsets,
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
  const availableWidth = Math.max(1, viewportWidth - pad * 2);
  const availableHeight = Math.max(1, viewportHeight - pad * 2);
  const zoom = Math.max(
    .25,
    Math.min(
      2.5,
      availableWidth / modelWidth,
      availableHeight / modelHeight,
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

function correctedResetLayout() {
  if (!el.viewport) return false;

  // Reset means geometry reset, not merely camera reset. Clear the persisted
  // node geometry and communication-port offsets, rebuild the authoritative
  // automatic layout, then fit that fresh layout to the *current* viewport.
  try {
    localStorage.removeItem(storageKey());
  } catch (_error) {
    // Local persistence is optional.
  }
  resetPortOffsets();

  const keepCapabilities = state.showCapabilities;
  state.selected.clear();
  state.view = {x: 28, y: 28, zoom: 1};
  autoLayout();
  state.showCapabilities = keepCapabilities;
  el.viewport.scrollLeft = 0;
  el.viewport.scrollTop = 0;
  render();

  // Persist the rebuilt geometry before fitting. In a detached window, the
  // camera itself remains local to that window while the reset node geometry is
  // still the shared model layout.
  persist();
  scheduleCorrectedFit({persistView: !detachedUtilityWindow});
  return true;
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

function installResetButtonOverride() {
  const resetButton = document.getElementById('oaDiagramReset');
  if (!resetButton || resetButton.dataset.correctedResetInstalled === 'true') return;
  resetButton.dataset.correctedResetInstalled = 'true';

  // The original Reset layout uses the old internal Fit implementation. Stop it
  // before it runs so reset and fit use one consistent viewport-aware path.
  resetButton.addEventListener('click', event => {
    event.preventDefault();
    event.stopImmediatePropagation();
    correctedResetLayout();
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
  installResetButtonOverride();
  installDetachedWindowFit();
  installFullscreenCorrection();
  window.oaCorrectedDiagramFit = correctedFitView;
  window.oaCorrectedDiagramReset = correctedResetLayout;
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', install, {once: true});
} else {
  install();
}
