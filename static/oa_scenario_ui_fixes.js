import {state, edgeId} from './oa_diagram_v2_state.js';

const TRAY_LAYOUT_VERSION = 1;
let trayObserver = null;
let trayGesture = null;
let boundResetButton = null;

const clean = value => String(value ?? '').replace(/\s+/g, ' ').trim();

function authoringActive() {
  const bar = document.getElementById('oaScenarioAuthoringBar');
  return state.mode === 'scenario' && Boolean(bar && !bar.hidden);
}

function currentScenarioActivityId() {
  const keys = [...state.selected].reverse();
  for (const key of keys) {
    if (!key.startsWith('node:')) continue;
    const id = key.slice(5);
    if (state.byId.get(id)?.type === 'OperationalActivity') return id;
  }
  return null;
}

function projectedExchangeById(diagramId) {
  const edges = Array.isArray(state.model?.edges) ? state.model.edges : [];
  for (let index = 0; index < edges.length; index += 1) {
    const edge = edges[index];
    if (edge?.type !== 'OPERATIONAL_EXCHANGE') continue;
    if (edgeId(edge, index) === diagramId) return edge;
  }
  return null;
}

function activityName(id) {
  return clean(state.byId.get(id)?.name || id || 'activity');
}

function showDirectionMessage(edge, currentActivityId) {
  const status = document.getElementById('oaDiagramStatus');
  if (!status || !edge) return;
  const exchange = clean(edge.name) || 'This interaction';
  const source = activityName(edge.source);
  const target = activityName(edge.target);
  const current = activityName(currentActivityId);

  if (edge.target === currentActivityId) {
    status.textContent = `"${exchange}" is incoming to ${current}: ${source} → ${target}. Operational Scenarios follow the stored interaction direction. Choose an outgoing interaction or correct the interaction direction in the model. A Communication Mean is not required.`;
  } else {
    status.textContent = `"${exchange}" is not connected as an outgoing interaction from ${current}. Operational Scenarios follow the stored interaction direction. A Communication Mean is not required.`;
  }
}

function guardIncomingScenarioInteraction(event) {
  if (!authoringActive()) return;
  const selectable = event.target.closest?.('[data-edge-type="OPERATIONAL_EXCHANGE"][data-edge-id]');
  if (!selectable) return;

  const currentActivityId = currentScenarioActivityId();
  if (!currentActivityId) return;
  const edge = projectedExchangeById(selectable.dataset.edgeId || '');
  if (!edge || edge.source === currentActivityId) return;

  event.preventDefault();
  event.stopPropagation();
  event.stopImmediatePropagation();
  showDirectionMessage(edge, currentActivityId);
}

function trayStorageKey() {
  return `oa-scenario-tray-layout:v${TRAY_LAYOUT_VERSION}:${state.session || 'default'}`;
}

function readTrayLayout() {
  try {
    return JSON.parse(localStorage.getItem(trayStorageKey()) || 'null');
  } catch (_error) {
    return null;
  }
}

function persistTrayLayout(tray) {
  if (!tray) return;
  const layout = {
    left: tray.offsetLeft,
    top: tray.offsetTop,
    width: tray.offsetWidth,
    height: tray.offsetHeight,
  };
  try {
    localStorage.setItem(trayStorageKey(), JSON.stringify(layout));
  } catch (_error) {
    // Diagram presentation persistence is optional.
  }
}

function clearTrayInlineLayout(tray) {
  if (!tray) return;
  ['left', 'top', 'right', 'bottom', 'width', 'height', 'maxHeight'].forEach(property => {
    tray.style[property] = '';
  });
  tray.classList.remove('is-user-positioned');
}

function clampTrayToTab(tray) {
  const tab = document.getElementById('diagramTab');
  if (!tray || !tab) return;
  const width = tray.offsetWidth;
  const height = tray.offsetHeight;
  const maxLeft = Math.max(0, tab.clientWidth - width - 6);
  const maxTop = Math.max(0, tab.clientHeight - height - 6);
  tray.style.left = `${Math.max(0, Math.min(maxLeft, tray.offsetLeft))}px`;
  tray.style.top = `${Math.max(0, Math.min(maxTop, tray.offsetTop))}px`;
}

function restoreTrayLayout(tray) {
  if (!tray) return;
  const session = state.session || 'default';
  if (tray.dataset.layoutSession === session) return;
  tray.dataset.layoutSession = session;
  clearTrayInlineLayout(tray);

  const saved = readTrayLayout();
  if (!saved) return;
  const left = Number(saved.left);
  const top = Number(saved.top);
  const width = Number(saved.width);
  const height = Number(saved.height);
  if (![left, top, width, height].every(Number.isFinite)) return;

  tray.classList.add('is-user-positioned');
  tray.style.left = `${left}px`;
  tray.style.top = `${top}px`;
  tray.style.right = 'auto';
  tray.style.bottom = 'auto';
  tray.style.width = `${Math.max(170, width)}px`;
  tray.style.height = `${Math.max(86, height)}px`;
  tray.style.maxHeight = 'none';
  requestAnimationFrame(() => clampTrayToTab(tray));
}

function endTrayGesture(event) {
  if (!trayGesture || (event.pointerId != null && event.pointerId !== trayGesture.pointerId)) return;
  const tray = trayGesture.tray;
  trayGesture = null;
  document.body.classList.remove('oa-scenario-tray-manipulating');
  persistTrayLayout(tray);
}

function moveTrayGesture(event) {
  const gesture = trayGesture;
  if (!gesture || event.pointerId !== gesture.pointerId) return;
  event.preventDefault();

  const tab = document.getElementById('diagramTab');
  if (!tab) return;
  const dx = event.clientX - gesture.startX;
  const dy = event.clientY - gesture.startY;

  if (gesture.kind === 'move') {
    const maxLeft = Math.max(0, tab.clientWidth - gesture.width - 6);
    const maxTop = Math.max(0, tab.clientHeight - gesture.height - 6);
    gesture.tray.style.left = `${Math.max(0, Math.min(maxLeft, gesture.left + dx))}px`;
    gesture.tray.style.top = `${Math.max(0, Math.min(maxTop, gesture.top + dy))}px`;
    return;
  }

  const maxWidth = Math.max(170, tab.clientWidth - gesture.left - 6);
  const maxHeight = Math.max(86, tab.clientHeight - gesture.top - 6);
  gesture.tray.style.width = `${Math.max(170, Math.min(maxWidth, gesture.width + dx))}px`;
  gesture.tray.style.height = `${Math.max(86, Math.min(maxHeight, gesture.height + dy))}px`;
}

function beginTrayGesture(event, kind) {
  if (event.button !== 0) return;
  const tray = event.currentTarget.closest('#oaScenarioTray');
  if (!tray) return;
  const tab = document.getElementById('diagramTab');
  if (!tab) return;

  event.preventDefault();
  event.stopPropagation();
  tray.classList.add('is-user-positioned');
  tray.style.left = `${tray.offsetLeft}px`;
  tray.style.top = `${tray.offsetTop}px`;
  tray.style.right = 'auto';
  tray.style.bottom = 'auto';
  tray.style.width = `${tray.offsetWidth}px`;
  tray.style.height = `${tray.offsetHeight}px`;
  tray.style.maxHeight = 'none';

  trayGesture = {
    kind,
    tray,
    pointerId: event.pointerId,
    startX: event.clientX,
    startY: event.clientY,
    left: tray.offsetLeft,
    top: tray.offsetTop,
    width: tray.offsetWidth,
    height: tray.offsetHeight,
  };
  document.body.classList.add('oa-scenario-tray-manipulating');
  event.currentTarget.setPointerCapture?.(event.pointerId);
}

function ensureTrayStyles() {
  if (document.getElementById('oaScenarioTrayLayoutStyle')) return;
  const style = document.createElement('style');
  style.id = 'oaScenarioTrayLayoutStyle';
  style.textContent = `
    #oaScenarioTray.oa-scenario-tray-manipulable {
      min-width: 170px;
      min-height: 86px;
      box-sizing: border-box;
    }
    #oaScenarioTray.oa-scenario-tray-manipulable .oa-scenario-tray-label {
      cursor: move;
      user-select: none;
      touch-action: none;
      padding-right: 22px;
    }
    #oaScenarioTray .oa-scenario-tray-resize {
      position: absolute;
      right: 2px;
      bottom: 2px;
      width: 20px;
      height: 20px;
      display: grid;
      place-items: center;
      padding: 0;
      border: 0;
      border-radius: 3px;
      background: rgba(255,255,255,.82);
      color: #5b6672;
      font-size: 12px;
      cursor: nwse-resize;
      touch-action: none;
      z-index: 4;
    }
    #oaScenarioTray .oa-scenario-tray-resize:hover,
    #oaScenarioTray .oa-scenario-tray-resize:focus-visible {
      color: #174a8b;
      background: #fff;
      outline: 2px solid rgba(23,74,139,.22);
    }
    body.oa-scenario-tray-manipulating {
      user-select: none;
    }
  `;
  document.head.appendChild(style);
}

function enhanceTray() {
  const tray = document.getElementById('oaScenarioTray');
  if (!tray) return;
  ensureTrayStyles();
  tray.classList.add('oa-scenario-tray-manipulable');
  restoreTrayLayout(tray);

  const label = tray.querySelector('.oa-scenario-tray-label');
  if (label && label.dataset.trayDragBound !== 'true') {
    label.dataset.trayDragBound = 'true';
    label.title = 'Drag to move Operational Scenarios';
    label.addEventListener('pointerdown', event => beginTrayGesture(event, 'move'));
  }

  let resize = tray.querySelector('.oa-scenario-tray-resize');
  if (!resize) {
    resize = document.createElement('button');
    resize.type = 'button';
    resize.className = 'oa-scenario-tray-resize';
    resize.textContent = '↘';
    resize.setAttribute('aria-label', 'Resize Operational Scenarios');
    resize.title = 'Drag to resize Operational Scenarios';
    resize.addEventListener('pointerdown', event => beginTrayGesture(event, 'resize'));
    tray.appendChild(resize);
  }

  const reset = document.getElementById('oaDiagramReset');
  if (reset && reset !== boundResetButton) {
    boundResetButton = reset;
    reset.addEventListener('click', () => {
      try { localStorage.removeItem(trayStorageKey()); } catch (_error) {}
      const current = document.getElementById('oaScenarioTray');
      if (current) {
        current.dataset.layoutSession = '';
        clearTrayInlineLayout(current);
      }
    });
  }
}

function installTrayObserver() {
  trayObserver?.disconnect();
  trayObserver = new MutationObserver(() => requestAnimationFrame(enhanceTray));
  trayObserver.observe(document.body, {childList: true, subtree: true});
  enhanceTray();
}

window.addEventListener('click', guardIncomingScenarioInteraction, {capture: true});
window.addEventListener('pointermove', moveTrayGesture, {capture: true});
window.addEventListener('pointerup', endTrayGesture, {capture: true});
window.addEventListener('pointercancel', endTrayGesture, {capture: true});
window.addEventListener('resize', () => {
  const tray = document.getElementById('oaScenarioTray');
  if (tray?.classList.contains('is-user-positioned')) clampTrayToTab(tray);
});

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', installTrayObserver, {once: true});
} else {
  installTrayObserver();
}
