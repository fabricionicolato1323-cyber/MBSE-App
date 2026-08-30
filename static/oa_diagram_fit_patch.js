import {
  state,
  visibleLayoutEntries,
  persist,
  autoLayout,
  storageKey,
  loadSaved,
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
const rawDetachedPanel = query.get('detachedPanel');
// In the unified docked sidebar, Diagram is its own output view. Only a
// separately undocked Diagram window needs an independent camera. Keep the old
// detached utility/Text URL as a migration fallback because it could contain the
// diagram in previous builds.
const detachedDiagramWindow = rawDetachedPanel === 'diagram' || rawDetachedPanel === 'utility';
const MAX_FIT_ZOOM = 1.0;
const FIT_PADDING = 56;
let firstDetachedDiagramFitDone = false;
let scheduledFitFrame = 0;

function correctedFitView({persistView = true} = {}) {
  if (!el.viewport) return false;
  const entries = visibleLayoutEntries();
  if (!entries.length) return false;

  el.viewport.classList.add('is-fit-view');
  el.viewport.scrollLeft = 0;
  el.viewport.scrollTop = 0;

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
  const availableWidth = Math.max(1, viewportWidth - FIT_PADDING * 2);
  const availableHeight = Math.max(1, viewportHeight - FIT_PADDING * 2);
  const zoom = Math.max(
    .25,
    Math.min(
      MAX_FIT_ZOOM,
      availableWidth / modelWidth,
      availableHeight / modelHeight,
    ),
  );

  state.view = {
    x: (viewportWidth - modelWidth * zoom) / 2 - minX * zoom,
    y: (viewportHeight - modelHeight * zoom) / 2 - minY * zoom,
    zoom,
  };
  applyView();
  renderEdges();

  requestAnimationFrame(() => {
    if (!el.viewport?.classList.contains('is-fit-view')) return;
    el.viewport.scrollLeft = 0;
    el.viewport.scrollTop = 0;
  });

  if (persistView && !detachedDiagramWindow) persist();
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

  const previouslySaved = loadSaved();

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

  const resetCamera = {...state.view};
  if (detachedDiagramWindow && previouslySaved?.view) {
    state.view = previouslySaved.view;
    persist();
    state.view = resetCamera;
  } else {
    persist();
  }

  scheduleCorrectedFit({persistView: !detachedDiagramWindow});
  return true;
}

function diagramIsVisible() {
  return Boolean(el.tab && el.tab.classList.contains('active') && !el.tab.hidden);
}

function releaseFittedCamera() {
  el.viewport?.classList.remove('is-fit-view');
}

function installFitButtonOverride() {
  const fitButton = document.getElementById('oaDiagramFit');
  if (!fitButton || fitButton.dataset.correctedFitInstalled === 'true') return;
  fitButton.dataset.correctedFitInstalled = 'true';

  fitButton.addEventListener('click', event => {
    event.preventDefault();
    event.stopImmediatePropagation();
    correctedFitView({persistView: !detachedDiagramWindow});
  }, true);
}

function installResetButtonOverride() {
  const resetButton = document.getElementById('oaDiagramReset');
  if (!resetButton || resetButton.dataset.correctedResetInstalled === 'true') return;
  resetButton.dataset.correctedResetInstalled = 'true';

  resetButton.addEventListener('click', event => {
    event.preventDefault();
    event.stopImmediatePropagation();
    correctedResetLayout();
  }, true);
}

function installManualCameraRelease() {
  el.viewport?.addEventListener('pointerdown', releaseFittedCamera, true);
  el.viewport?.addEventListener('wheel', releaseFittedCamera, {capture: true, passive: true});
  document.getElementById('oaDiagramZoomIn')?.addEventListener('click', releaseFittedCamera, true);
  document.getElementById('oaDiagramZoomOut')?.addEventListener('click', releaseFittedCamera, true);
}

function installDetachedWindowFit() {
  if (!detachedDiagramWindow) return;

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
    scheduleCorrectedFit({persistView: !detachedDiagramWindow});
  });
}

function installResizeCorrection() {
  window.addEventListener('resize', () => {
    if (!diagramIsVisible() || !el.viewport?.classList.contains('is-fit-view')) return;
    scheduleCorrectedFit({persistView: !detachedDiagramWindow});
  });
}

function install() {
  installFitButtonOverride();
  installResetButtonOverride();
  installManualCameraRelease();
  installDetachedWindowFit();
  installFullscreenCorrection();
  installResizeCorrection();
  window.oaCorrectedDiagramFit = correctedFitView;
  window.oaCorrectedDiagramReset = correctedResetLayout;
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', install, {once: true});
} else {
  install();
}
