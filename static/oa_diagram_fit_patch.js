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
const detachedUtilityWindow = query.get('detachedPanel') === 'utility';
const MAX_FIT_ZOOM = 1.0;
const FIT_PADDING = 56;
let firstDetachedDiagramFitDone = false;
let scheduledFitFrame = 0;

function correctedFitView({persistView = true} = {}) {
  if (!el.viewport) return false;
  const entries = visibleLayoutEntries();
  if (!entries.length) return false;

  // A fitted camera should not inherit native scrollbar offsets from a previous
  // pan/zoom state. Hide native overflow while fitted; any manual camera gesture
  // restores the normal scrollable viewport.
  el.viewport.classList.add('is-fit-view');
  el.viewport.scrollLeft = 0;
  el.viewport.scrollTop = 0;

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
  const availableWidth = Math.max(1, viewportWidth - FIT_PADDING * 2);
  const availableHeight = Math.max(1, viewportHeight - FIT_PADDING * 2);

  // Fit means "show the whole model", not "magnify the model". The previous
  // 2.5x ceiling made a compact automatic layout look over-zoomed in full screen.
  // Full-screen real estate is now used by the canvas itself, while Fit never
  // enlarges geometry above its natural 100% scale.
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

  // Re-assert the fitted origin after transforms/layout settle. Some browsers
  // preserve a native scroll offset when entering fullscreen if overflow was
  // scrollable immediately beforehand.
  requestAnimationFrame(() => {
    if (!el.viewport?.classList.contains('is-fit-view')) return;
    el.viewport.scrollLeft = 0;
    el.viewport.scrollTop = 0;
  });

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

  // Keep the main-window camera when Reset is initiated from a detached browser
  // window. Geometry is shared, but each window must keep its own camera.
  const previouslySaved = loadSaved();

  // Reset means geometry reset, not merely camera reset. Clear the persisted
  // node geometry and communication-port offsets, rebuild the authoritative
  // automatic layout, then fit that fresh layout to the current viewport.
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

  // Persist the rebuilt node geometry. In a detached window preserve the camera
  // previously stored by the docked application instead of replacing it with
  // this detached window's temporary reset camera.
  const resetCamera = {...state.view};
  if (detachedUtilityWindow && previouslySaved?.view) {
    state.view = previouslySaved.view;
    persist();
    state.view = resetCamera;
  } else {
    persist();
  }

  scheduleCorrectedFit({persistView: !detachedUtilityWindow});
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

function installManualCameraRelease() {
  // Fit intentionally hides native overflow. The instant the user manually pans,
  // zooms, selects a zoom rectangle or presses +/- we return to normal scrollable
  // navigation before the interaction layer handles that gesture.
  el.viewport?.addEventListener('pointerdown', releaseFittedCamera, true);
  el.viewport?.addEventListener('wheel', releaseFittedCamera, {capture: true, passive: true});
  document.getElementById('oaDiagramZoomIn')?.addEventListener('click', releaseFittedCamera, true);
  document.getElementById('oaDiagramZoomOut')?.addEventListener('click', releaseFittedCamera, true);
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

function installResizeCorrection() {
  window.addEventListener('resize', () => {
    if (!diagramIsVisible() || !el.viewport?.classList.contains('is-fit-view')) return;
    scheduleCorrectedFit({persistView: !detachedUtilityWindow});
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